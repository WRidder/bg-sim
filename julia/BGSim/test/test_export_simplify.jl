# Folded parameters substituted and simplified before the Jacobian and the C code
# (plan/EXPORT_PLAN.md D-EX10, src/export/simplify.jl):
#
#   * the rules: constant subtrees are evaluated, `0*x`, `1*x`, `x+0`, `x^1` vanish, a
#     constant `ifelse` condition selects its branch, `&`/`|` with a constant reduce; a domain
#     error and an unfolded parameter stay symbolic;
#   * the emitter's peephole (`_c_product`, `_c_sum`) never writes `0.0 * x`, `1.0 * x` or
#     `(-1.0) * x`, and is off with `simplify = false`;
#   * a zero-valued folded coupling leaves the Jacobian pattern (and the C), a tunable one
#     stays a runtime parameter with its entries, `fold_parameters = false` substitutes
#     nothing, and the report counts operations and non-zeros before and after;
#   * with gcc on PATH, the simplified and the unsimplified C give the same trajectory.

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile
import Symbolics

const _SI = BGSim.Export

_si_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

# Two lags coupled through `k` (0 by default): with `k` folded the coupling is structurally
# gone, so the Jacobian is diagonal. `ax`/`ay`/`az` are a unit axis, as in the mechanics
# blocks, whose norm is a constant observed value once they are folded.
function _si_pair(; k_attrs = "")
    return """
    @block Pair begin
        @inputs u::Real
        @outputs y::Real
        @parameters k::Real = 0.0$(k_attrs)
        @parameters a::Real = 2.0
        @parameters ax::Real = 0.0
        @parameters ay::Real = 0.0
        @parameters az::Real = 1.0
        @variables x1::Real = 0.0
        @variables x2::Real = 1.0
        @variables s::Real
        @equations begin
            s ~ ax * ax + ay * ay + az * az
            ddt(x1) ~ -a * x1 + k * x2 + s * u
            ddt(x2) ~ -x2 + k * sin(x1) + ax * x1
            y ~ x1 + x2
        end
    end
    """
end

function _si_model(; k_attrs = "")
    nodes = Any[bg_node("n2", "P", _si_inline(_si_pair(; k_attrs))),
        bg_node("n1", "U", bg_ref("stdlib:converters/ExportInput");
            params = Dict{String,Any}("value" => "1.5")),
        bg_node("n3", "Y", bg_ref("stdlib:converters/ExportOutput"))]
    conns = Any[bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "signal", "n2", "y", "n3", "u")]
    return bg_model("SimplifyPair", nodes, conns; t_end = 0.2, points = 21)
end

_si_flat(doc) = Compile.flatten(IR.parse_model(doc))

# `0.0 * x`, `1.0 * x`, `x * 1.0` and `(-1.0) * x` in the generated C (comments excluded).
function _si_leftovers(model_c)
    code = join((first(split(l, "/*")) for l in split(model_c, '\n')), "\n")
    return length(collect(eachmatch(
        r"(?<![0-9.e])0\.0 \*|\* 0\.0(?![0-9e])|(?<![0-9.e])1\.0 \*|\* 1\.0(?![0-9e])|\(-1\.0\) \*", code)))
end

@testset "export simplification (D-EX10)" begin
    Symbolics.@variables x y p q t
    X, Y, P, Q, T = Symbolics.unwrap.((x, y, p, q, t))
    subs = Dict{Any,Any}(P => 0.0, Q => 1.0)
    fs(e, s = subs) = _SI.fold_simplify(Symbolics.unwrap(e), s, IdDict{Any,Any}())
    env = Dict{Any,String}(X => "x[0]", Y => "x[1]", T => "t", P => "m->p[0]", Q => "m->p[1]")
    c(e) = _SI.cexpr(_SI.as_symbolic(e), env)

    @testset "rules" begin
        @test isequal(fs(P * X + Q * Y), Y)                  # 0*x -> 0, 1*y -> y, x + 0 -> x
        @test fs(P * P + Q * Q) === 1.0                      # a constant subtree is a number
        @test fs(sin(P) * X) == 0
        @test isequal(fs(cos(P) * X), X)
        @test isequal(fs(X^Q), X)                            # x^1 -> x
        @test isequal(fs(X / (Q + P)), X)                    # x / 1 -> x
        @test isequal(fs(2.0 * Q * X), 2.0 * X)              # coefficients merge
        @test isequal(fs(ifelse(Q > 0, X, Y)), X)            # constant condition: its branch
        @test isequal(fs(ifelse(P > 0, X, Y)), Y)
        @test fs(ifelse(X > 0, P * X, 0)) == 0               # both branches 0
        @test isequal(fs((X > 0) & (Q > 0)), Symbolics.unwrap(X > 0))
        @test fs((X > 0) | (Q > 0)) === true
        @test fs((X > 0) & (P > 0)) === false
        @test isequal(fs(T * P + X), X)                      # t * 0 drops t
        # A domain error is left for C; a value that is not folded stays symbolic, and an
        # expression without folded values is returned as it is.
        @test !(fs(sqrt(-Q) * X) isa Number)
        e = Symbolics.unwrap(P * X + sin(Q * Y))
        @test fs(e, Dict{Any,Any}()) === e
        @test isequal(fs(P * X + Q * Y, Dict{Any,Any}(Q => 1.0)), Symbolics.unwrap(P * X + Y))
        # A constant result becomes a SymbolicUtils constant for the rest of the export.
        k = _SI.as_symbolic(1.5)
        @test _SI._try_const(k) == 1.5 && isempty(Symbolics.get_variables(k))
    end

    @testset "emitter peephole" begin
        @test _SI._c_product(["0.0", "x[0]"]) == "0.0"
        @test _SI._c_product(["1.0", "x[0]"]) == "x[0]"
        @test _SI._c_product(["x[0]", "1.0", "x[1]"]) == "(x[0] * x[1])"
        @test _SI._c_product(["(-1.0)", "x[0]", "x[1]"]) == "(-(x[0] * x[1]))"
        @test _SI._c_product(["2.0", "3.0"]) == "6.0"
        @test _SI._c_product(["2.0", "x[0]"]) == "(2.0 * x[0])"
        @test _SI._c_product(["NAN", "x[0]"]) == "(NAN * x[0])"   # not a finite literal
        @test _SI._lit_value("(-2.5e-3)") == -2.5e-3 && _SI._lit_value("x[0]") === nothing
        @test c(X - Y) == "(x[0] - x[1])"
        @test c(-X - Y) in ("(-x[0] - x[1])", "(-x[1] - x[0])")
        @test c(2.0 - 3.0 * X) == "(2.0 - (3.0 * x[0]))"
        @test c(-X) == "(-x[0])"
        # Symbolic parameters reach the emitter as literals through `env` when they are not
        # substituted (tables): the peephole still drops them.
        lit = Dict{Any,String}(X => "x[0]", P => "0.0", Q => "1.0")
        @test _SI.cexpr(P * X, lit) == "0.0"
        @test _SI.cexpr(Q * X, lit) == "x[0]"
        @test _SI.cexpr(X + P, lit) == "x[0]"
        @test _SI.cexpr(X^Q, lit) == "x[0]"
        @test _SI.cexpr(X / Q, lit) == "x[0]"
        # Off: the C as written before (D-EX10 comparison runs).
        Base.ScopedValues.with(_SI.C_SIMPLIFY => false) do
            @test _SI.cexpr(X - Y, env) == "(((-1.0) * x[1]) + x[0])" ||
                  _SI.cexpr(X - Y, env) == "(x[0] + ((-1.0) * x[1]))"
            @test _SI.cexpr(P * X, lit) == "(0.0 * x[0])"
        end
    end

    @testset "a zero folded coupling leaves the Jacobian" begin
        settings(; kw...) = _SI.ExportSettings(; t_end = 0.2, method = :ros2, dt = 1e-3, kw...)
        on = _SI.export_model(_si_flat(_si_model()), mktempdir(); settings = settings())
        off = _SI.export_model(_si_flat(_si_model()), mktempdir();
            settings = settings(simplify = false))
        @test on.ok && off.ok
        s = on.report["simplify"]
        @test s["enabled"] && s["jacobianNnzBefore"] == 4 && s["jacobianNnz"] == 2
        @test s["rhsOps"] < s["rhsOpsBefore"]
        @test s["constantObserved"] >= 1                     # s = |axis|^2 = 1
        @test s["luNnz"] < s["luNnzBefore"]
        @test on.report["linearAlgebra"]["nnzJ"] == 2
        @test on.report["jacobian"]["entries"] == 2
        @test off.report["linearAlgebra"]["nnzJ"] == 4
        @test !off.report["simplify"]["enabled"]
        @test off.report["simplify"]["rhsOps"] == off.report["simplify"]["rhsOpsBefore"]
        @test on.report["guid"] != off.report["guid"]
        c_on = read(joinpath(on.dir, "sources", "model.c"), String)
        c_off = read(joinpath(off.dir, "sources", "model.c"), String)
        @test _si_leftovers(c_on) == 0
        @test _si_leftovers(c_off) > 0
        @test !occursin("sin(", c_on)                        # k * sin(x1) is gone
        @test occursin("sin(", c_off)
        @test _SI.ExportSettings(Dict("simplify" => false)).simplify == false
        @test _SI.ExportSettings(Dict{String,Any}()).simplify

        # fold_parameters = false: every parameter is a runtime value, nothing is
        # substituted, so the coupling stays.
        rt = _SI.export_model(_si_flat(_si_model()), mktempdir();
            settings = settings(fold_parameters = false))
        @test rt.ok && rt.report["folded"] == 0
        @test rt.report["linearAlgebra"]["nnzJ"] == 4
        @test rt.report["simplify"]["jacobianNnz"] == rt.report["simplify"]["jacobianNnzBefore"]
        @test occursin("m->p[", read(joinpath(rt.dir, "sources", "model.c"), String))
    end

    @testset "a tunable parameter stays symbolic" begin
        r = _SI.export_model(_si_flat(_si_model(k_attrs = ", [tunable = true, min = 0.0, max = 1.0]")),
            mktempdir(); settings = _SI.ExportSettings(t_end = 0.2, method = :ros2, dt = 1e-3))
        @test r.ok
        @test [p["name"] for p in r.report["parameters"]] == ["P/k"]
        @test r.report["linearAlgebra"]["nnzJ"] == 4         # k * x2 and k * sin(x1) stay
        # ax * x1 is gone, but k * sin(x1) keeps entry (2, 1)
        @test r.report["simplify"]["jacobianNnz"] == 4
        @test r.report["simplify"]["rhsOps"] < r.report["simplify"]["rhsOpsBefore"]
        model_c = read(joinpath(r.dir, "sources", "model.c"), String)
        @test occursin("m->p[0]", model_c) && occursin("sin(", model_c)
    end

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export simplification: no gcc on PATH, the C comparison is skipped"
    else
        @testset "simplified and unsimplified C agree" begin
            runner = raw"""
            #include <stdio.h>
            #include "model.h"
            static bg_model m;
            int main(void) {
                bg_reset(&m, 0.0);
                for (int k = 0; k < 200; ++k) if (bg_step(&m) != 0) return 2;
                bg_update_outputs(&m);
                for (int i = 0; i < BG_NX; ++i) printf("%.17g\n", m.x[i]);
                for (int i = 0; i < BG_NY; ++i) printf("%.17g\n", m.y[i]);
                return 0;
            }
            """
            function run_c(simplify, method)
                dir = mktempdir()
                r = _SI.export_model(_si_flat(_si_model()), dir; settings = _SI.ExportSettings(
                    t_end = 0.2, method = method, dt = 1e-3, simplify = simplify))
                @test r.ok
                src = joinpath(dir, "sources")
                write(joinpath(dir, "runner.c"), runner)
                exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
                files = [joinpath(src, f) for f in ("model.c", "bg_solver.c")]
                run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $(joinpath(dir, "runner.c")) -o $exe -lm`)
                return parse.(Float64, readlines(`$exe`))
            end
            for method in (:rk4, :ros2)
                a, b = run_c(true, method), run_c(false, method)
                @test length(a) == length(b)
                @test maximum(abs.(a .- b)) <= 1e-12 * max(1.0, maximum(abs, b))
            end
        end
    end
end
