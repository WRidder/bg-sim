# Work package J-EX1: the C/FMU export (plan/EXPORT_PLAN.md).
#
# The acceptance of the work package on small models through the real pipeline:
#   * the interface is exactly the Export markers (input, output) plus the tunable
#     parameters, with their declared ranges; every other parameter is folded;
#   * the step comes from the spectrum, including the declared range of a tunable parameter
#     the Jacobian depends on (D-EX16): a first-order lag with tau in [1 ms, 1 s] has
#     |λ| up to 1000 1/s, so RK4 at 0.3 accuracy needs 4 substeps per 1 ms;
#   * refusals name the construct: `@events` (E110), a mass-matrix DAE (E111), no markers
#     (W209), a tunable parameter without a range (W210), a forced unstable step (W207);
#   * when a C compiler is on PATH, the generated sources compile with -Werror, the hot path
#     does not allocate after instantiate, and the FMU's answer matches the analytic one.

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile
import JSON3
import LinearAlgebra

const _EX = BGSim.Export

_ex_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

const _EX_LAG = """
@block Lag begin
    @inputs u::Real
    @outputs y::Real
    @parameters tau::Real = 0.01, [unit = "s", tunable = true, min = 0.001, max = 1.0]
    @parameters gain::Real = 1.0
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (gain * u - x) / tau
        y ~ x
    end
end
"""

# An index-1 DAE that MTK cannot reduce: z solves a cubic in the state x, the input u and
# t, so the compiled system keeps one algebraic equation (mass-matrix row 0).
const _EX_DAE = """
@block DaeLag begin
    @inputs u::Real
    @outputs y::Real
    @parameters tau::Real = 0.05
    @parameters w::Real = 10.0
    @variables x::Real = 0.0
    @variables z::Real = 1.0
    @equations begin
        ddt(x) ~ (z - x) / tau
        z^3 + z ~ u + x + sin(w * t)
        y ~ x + z
    end
end
"""

# The DAE's answer y(t_end) with u = 2: the reduced ODE x' = (z(x, t) - x) / tau, z by
# Newton, RK4 at 1 µs.
function _ex_dae_reference(t_end; u = 2.0, tau = 0.05, w = 10.0)
    zof(x, t) = (z = 1.0; for _ in 1:60; z -= (z^3 + z - u - x - sin(w * t)) / (3z^2 + 1); end; z)
    f(x, t) = (zof(x, t) - x) / tau
    h = 1e-6
    x = 0.0
    for n in 0:round(Int, t_end / h) - 1
        t = n * h
        k1 = f(x, t); k2 = f(x + h / 2 * k1, t + h / 2)
        k3 = f(x + h / 2 * k2, t + h / 2); k4 = f(x + h * k3, t + h)
        x += h / 6 * (k1 + 2k2 + 2k3 + k4)
    end
    return x + zof(x, t_end)
end

# FIX-M2-3's DAE fixture (test_discrete.jl): `b` stays algebraic, and the held output `u` of
# a 0.25 s sampler steps 0 -> 1 at the 1.0 s tick, so `b` must re-solve while `a` keeps its
# value: a(t) = 2(1 - e^(-t/2)) up to 1 s, then 4 - (4 - a(1)) e^(-(t - 1)/2).
const _EX_DAE_PLANT = """
@block DaePlant begin
    @inputs u::Real
    @outputs x::Real = 0.0
    @variables begin
        a::Real = 0.0, [state = :prefer]
        b::Real = 0.0
    end
    @equations begin
        ddt(a) ~ -0.5 * a + 1.0 + u
        b^3 + b ~ a + 2.0 * u
        x ~ a
    end
end
"""

const _EX_DAE_SAMPLER = """
@block QuarterSampler begin
    @inputs ref::Real
    @outputs u::Real = 0.0
    @discrete Ts = 0.25 begin
        u = hold(ref)
    end
end
"""

function _ex_dae_sampled_model()
    nodes = Any[bg_node("n1", "P1", _ex_inline(_EX_DAE_PLANT)),
        bg_node("n2", "S1", _ex_inline(_EX_DAE_SAMPLER)),
        bg_node("n3", "R1", bg_ref("stdlib:sources/Step");
            params = Dict{String,Any}("t_step" => "1.0", "initial" => "0.0", "final" => "1.0"))]
    conns = Any[bg_conn("c1", "signal", "n3", "y", "n2", "ref"),
        bg_conn("c2", "signal", "n2", "u", "n1", "u")]
    return bg_model("DaeSampled", nodes, conns; t_end = 2.0, points = 21)
end

# A plain C driver: n steps through the C API, then every output and local.
const _EX_DRIVER = """
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model g_m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 0;
    bg_reset(&g_m, 0.0);
    for (long k = 0; k < n; ++k)
        if (bg_step(&g_m) != 0) { printf("step failed at %ld\\n", k); return 3; }
    bg_update_outputs(&g_m);
    for (int i = 0; i < BG_NY; ++i) printf("%.17g\\n", g_m.y[i]);
    return 0;
}
"""

# The same driver, printing the states instead.
const _EX_DRIVER_X = replace(_EX_DRIVER, "    bg_update_outputs(&g_m);\n    for (int i = 0; i < BG_NY; ++i) printf(\"%.17g\\n\", g_m.y[i]);" =>
    "    for (int i = 0; i < BG_NX; ++i) printf(\"%.17g\\n\", g_m.x[i]);")

const _EX_EXAMPLES = normpath(joinpath(@__DIR__, "..", "..", "..", "examples"))

function _ex_lag_model(; lag = _EX_LAG, markers = true)
    nodes = Any[bg_node("n2", "Plant", _ex_inline(lag))]
    conns = Any[]
    if markers
        push!(nodes, bg_node("n1", "U", bg_ref("stdlib:converters/ExportInput");
            params = Dict{String,Any}("value" => "2.0")))
        push!(nodes, bg_node("n3", "Y", bg_ref("stdlib:converters/ExportOutput")))
        push!(conns, bg_conn("c1", "signal", "n1", "y", "n2", "u"))
        push!(conns, bg_conn("c2", "signal", "n2", "y", "n3", "u"))
    else
        push!(nodes, bg_node("n1", "C", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("k" => "2.0")))
        push!(conns, bg_conn("c1", "signal", "n1", "y", "n2", "u"))
    end
    return bg_model("ExportLag", nodes, conns; t_end = 0.1, points = 11)
end

_ex_flat(doc) = Compile.flatten(IR.parse_model(doc))
_ex_codes(r) = Set(d.code for d in r.diagnostics)

@testset "export (J-EX1)" begin
    @testset "interface, folding and the ranged step" begin
        dir = mktempdir()
        r = _EX.export_model(_ex_flat(_ex_lag_model()), dir;
            settings = _EX.ExportSettings(t_end = 0.1))
        @test r.ok
        @test !("W209" in _ex_codes(r))
        @test !("W210" in _ex_codes(r))
        rep = r.report
        @test [i["name"] for i in rep["inputs"]] == ["U"]
        @test rep["inputs"][1]["start"] == 2.0
        @test [o["name"] for o in rep["outputs"]] == ["Y"]
        @test [p["name"] for p in rep["parameters"]] == ["Plant/tau"]
        @test rep["parameters"][1]["variability"] == "tunable"
        @test rep["folded"] >= 1                     # Plant/gain is a literal now
        @test isempty(rep["locals"])
        @test rep["spectrum"]["rangedValues"] == 1
        @test isapprox(rep["spectrum"]["maxAbsLambda"], 1000.0; rtol = 1e-9)
        @test rep["dt"] == 2.5e-4 && rep["substeps"] == 4
        @test rep["method"] == "rk4"

        xml = read(joinpath(dir, "modelDescription.xml"), String)
        @test occursin("name=\"U\" valueReference=\"2\" causality=\"input\"", xml)
        @test occursin("name=\"Y\" valueReference=\"0\" causality=\"output\"", xml)
        @test occursin("min=\"0.001\" max=\"1.0\"", xml)
        model_c = read(joinpath(dir, "sources", "model.c"), String)
        @test !occursin("Plant/gain", model_c)       # folded, so no parameter comment
        @test occursin("m->u[0]", model_c) && occursin("m->p[0]", model_c)
        @test isfile(joinpath(dir, "sources", "bg_solver.c"))
        @test isfile(joinpath(dir, "export.json"))
    end

    @testset "expose_all adds read-only locals, not interface" begin
        r = _EX.export_model(_ex_flat(_ex_lag_model()), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.1, expose_all = true))
        @test r.ok
        @test "Plant/x" in r.report["locals"]
        @test [o["name"] for o in r.report["outputs"]] == ["Y"]
    end

    @testset "diagnostics" begin
        r = _EX.export_model(_ex_flat(_ex_lag_model(markers = false)), mktempdir())
        @test r.ok && "W209" in _ex_codes(r)

        unranged = replace(_EX_LAG, ", min = 0.001, max = 1.0" => "")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = unranged)), mktempdir())
        @test r.ok && "W210" in _ex_codes(r)

        # tau down to 0.1 ms: |λ| = 1e4, RK4 is stable only below 0.279 ms, so a forced 1 ms
        # step is reported as divergent.
        fast = replace(_EX_LAG, "min = 0.001" => "min = 0.0001")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = fast)), mktempdir();
            settings = _EX.ExportSettings(dt = 1e-3))
        @test r.ok && "W207" in _ex_codes(r)

        r = _EX.export_model(_ex_flat(_ex_lag_model()), mktempdir();
            settings = _EX.ExportSettings(dt = 3e-4))
        @test !r.ok && "E104" in _ex_codes(r)         # 0.3 ms does not divide 1 ms

        events = replace(_EX_LAG, "    @equations begin" => """
            @events begin
                x > 1.5 => begin
                    reinit(x, 0.0)
                end
            end
            @equations begin""")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = events)), mktempdir())
        @test !r.ok && "E110" in _ex_codes(r)

        # A DAE: RK4 refuses it (E111), auto picks a Rosenbrock method (J-EX3).
        dae = replace(_EX_LAG, "        y ~ x\n" => "        y^3 + y ~ x\n")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = dae)), mktempdir();
            settings = _EX.ExportSettings(method = :rk4))
        @test !r.ok && "E111" in _ex_codes(r)
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = dae)), mktempdir())
        @test r.ok && r.report["method"] in ("ros2", "ros34pw2", "rodas4p")
    end

    @testset "step choice" begin
        @test _EX.stable_step(:rk4, [-1000.0 + 0im]) ≈ 2.785293563405282e-3 rtol = 1e-9
        @test _EX.stable_step(:euler, [-1000.0 + 0im]) ≈ 2.0e-3 rtol = 1e-9
        @test _EX.stable_step(:rk4, [0.0 + 1im]) == Inf  # a neutral mode does not limit h
        c = _EX.choose_step(:rk4, [(0.0, ComplexF64[-3870.8])], Int64(1_000_000))
        @test c.dt_ns * c.substeps == 1_000_000 && c.dt_ns / 1e9 <= 0.3 / 3870.8
    end

    @testset "settings from JSON" begin
        s = _EX.ExportSettings(Dict("dt" => 1e-4, "method" => "RK4", "expose_all" => true))
        @test s.dt == 1e-4 && s.method === :rk4 && s.expose_all && s.step == 1e-3
        s = _EX.ExportSettings(Dict("method" => "Rodas4P", "jacobian" => "FD"))
        @test s.method === :rodas4p && s.jacobian === :fd
    end

    @testset "Rosenbrock tableaus, stability and the cost model (J-EX3)" begin
        # The Julia copy of the tableaus (and so bg_solver.c's) is OrdinaryDiffEq's.
        tabs = BGSim.OrdinaryDiffEqRosenbrock.OrdinaryDiffEqRosenbrockTableaus
        for (m, ref) in (:ros2 => tabs.ROS2RodasTableau(Float64, Float64),
                         :ros34pw2 => tabs.ROS34PW2RodasTableau(Float64, Float64),
                         :rodas4p => tabs.Rodas4PTableau(Float64, Float64))
            t = _EX.ROSENBROCK_TABLEAUS[m]
            s = length(t.b)
            @test t.gamma == ref.gamma && t.b == ref.b && t.c == ref.c[1:s] && t.d == ref.d[1:s]
            @test t.a == ref.A[1:s, 1:s] && t.c_[2:s, 1:s-1] == ref.C[2:s, 1:s-1]
        end
        # ROS2's stability function in closed form: (1 + (1 - 2γ) z) / (1 - γ z)^2.
        γ = 1 + 1 / sqrt(2)
        @test _EX.stability_function(:ros2, -1.0) ≈ (1 + (1 - 2γ) * -1) / (1 + γ)^2 rtol = 1e-12
        for m in _EX.ROSENBROCK_METHODS
            @test _EX.amplification(m, -1e9) < 1e-5                  # L-stable
            @test _EX.amplification(m, -2.0 + 30im) < 1               # A-stable
            @test _EX.stable_step(m, [-1e6 + 0im, -10.0 + 1e4im]) == Inf
            # order p: the local error on y' = λy shrinks like z^(p+1)
            p = _EX.ROSENBROCK_TABLEAUS[m].order
            e(z) = abs(_EX.stability_function(m, z) - exp(z))
            @test log2(e(-0.02) / e(-0.01)) ≈ p + 1 atol = 0.2
        end
        # A stiff parasitic mode is damped in one Rosenbrock step; RK4 must resolve it.
        stiff = [(0.0, ComplexF64[-1e7, -5.0])]
        c = _EX.choose_step(:ros2, stiff, Int64(1_000_000))
        @test c.substeps == 1 && !c.over_budget
        @test _EX.choose_step(:rk4, stiff, Int64(1_000_000)).over_budget
        # A real fast mode (the dc-motor current) is resolved: RK4 is cheaper there.
        motor = [(0.0, ComplexF64[-3870.8, -12.0])]
        best, table = _EX.choose_method((:rk4, _EX.ROSENBROCK_METHODS...), motor,
            Int64(1_000_000), 3; f_ops = 30, jac_ops = m -> 20.0)
        @test best.method === :rk4 && length(table) == 4
        best, _ = _EX.choose_method((:rk4, _EX.ROSENBROCK_METHODS...), stiff,
            Int64(1_000_000), 3; f_ops = 30, jac_ops = m -> 20.0)
        @test _EX.is_rosenbrock(best.method) && best.substeps == 1
        # The finite spectrum of a DAE: x' = -2x + z, 0 = x - 4z  ->  λ = -2 + 1/4.
        @test _EX.pencil_eigvals([-2.0 1.0; 1.0 -4.0], [1.0, 0.0]) ≈ [-1.75]
        @test_throws LinearAlgebra.SingularException _EX.pencil_eigvals(
            [-2.0 1.0; 1.0 0.0], [1.0, 0.0])
    end

    @testset "an index-1 DAE exports with a Rosenbrock method" begin
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = _EX_DAE)), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.2))
        @test r.ok
        rep = r.report
        @test rep["algebraic"] == 1 && rep["states"] == 2
        @test rep["method"] == "ros2" && rep["dt"] == 1e-3   # |λ| ≈ 17 1/s: one ROS2 step
        @test rep["jacobian"]["kind"] == "symbolic" && rep["dependsOnTime"]
        @test [s["method"] for s in rep["selection"]] == ["ros2", "ros34pw2", "rodas4p"]
        model_c = read(joinpath(r.dir, "sources", "model.c"), String)
        @test occursin("0 = residual (algebraic", model_c)
        @test occursin("bg_mass[BG_SZ(2)]", model_c)
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = _EX_DAE)), mktempdir();
            settings = _EX.ExportSettings(method = :euler))
        @test !r.ok && "E111" in _ex_codes(r)
    end

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export: no gcc on PATH, the compile-and-run checks are skipped"
    else
        @testset "compiles, does not allocate, matches the analytic lag" begin
            dir = mktempdir()
            r = _EX.export_model(_ex_flat(_ex_lag_model()), dir;
                settings = _EX.ExportSettings(t_end = 0.1))
            src = joinpath(dir, "sources")
            harness = joinpath(_EX.RUNTIME_DIR, "alloc_check.c")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -c $(files[1]) -I $src -o $(joinpath(dir, "m.o"))`)
            @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
            # 100 doSteps of 1 ms (4 internal steps each): t = 0.1 s.
            out = read(`$exe 4 100`, String)
            @test occursin("after instantiate 0", out)
            y = parse(Float64, match(r"y\[0\] = (\S+)", out).captures[1])
            @test isapprox(y, 2.0 * (1 - exp(-0.1 / 0.01)); rtol = 1e-7)
        end

        # The DAE through each Rosenbrock method in C: -Werror, C++17, no allocation, and
        # y(0.2) against the reference with the method's order of convergence (dt 10 ms and
        # 5 ms, 20 doSteps of 10 ms); the finite-difference Jacobian gives the same answer.
        @testset "Rosenbrock DAE in C: $(m)" for m in (:ros2, :ros34pw2, :rodas4p)
            ref = _ex_dae_reference(0.2)
            cxx = Sys.which("g++")
            errs = Float64[]
            for (dt, jac) in ((1e-2, :auto), (5e-3, :auto), (5e-3, :fd))
                dir = mktempdir()
                r = _EX.export_model(_ex_flat(_ex_lag_model(lag = _EX_DAE)), dir;
                    settings = _EX.ExportSettings(t_end = 0.2, step = 1e-2, dt = dt,
                        method = m, jacobian = jac))
                @test r.ok && r.report["method"] == String(m)
                @test r.report["jacobian"]["kind"] == (jac === :fd ? "finite-difference" : "symbolic")
                src = joinpath(dir, "sources")
                exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
                files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
                for f in files
                    @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -c $f -I $src -o $(joinpath(dir, "o.o"))`)
                end
                cxx === nothing || @test success(`$cxx -x c++ -std=c++17 -fsyntax-only -Wall -Werror -I $src $(files[1]) $(files[2])`)
                @test success(`$cc -std=c11 -O2 -I $src $(joinpath(_EX.RUNTIME_DIR, "alloc_check.c")) $files -o $exe -lm`)
                out = read(`$exe $(round(Int, 1e-2 / dt)) 20`, String)
                @test occursin("after instantiate 0", out)
                y = parse(Float64, match(r"y\[0\] = (\S+)", out).captures[1])
                push!(errs, abs(y - ref))
            end
            p = _EX.ROSENBROCK_TABLEAUS[m].order
            @test errs[1] < 1e-2 * abs(ref)
            @test log2(errs[1] / errs[2]) > p - 0.5
            @test isapprox(errs[3], errs[2]; rtol = 0.05, atol = 1e-9 * abs(ref))
        end

        # drivetrain/bondgraph keeps the rotor acceleration as an algebraic unknown (the rotor
        # inertia is rigidly geared to the wheel). Its W needs row interchanges at a later
        # pivot: the dense solve once applied them in LINPACK order to LAPACK-stored factors
        # and was 0.7 % off after 2 ms. Rodas4P at 0.1 ms must match a tight Julia solve.
        @testset "row interchanges in the dense LU (drivetrain/bondgraph)" begin
            pdir = joinpath(_EX_EXAMPLES, "drivetrain")
            doc = JSON3.read(read(joinpath(pdir, "models", "bondgraph.bgmodel.json"), String),
                Dict{String,Any})
            flat = Compile.flatten(IR.parse_model(doc); project_dir = pdir)
            dir = mktempdir()
            r = _EX.export_model(flat, dir; settings = _EX.ExportSettings(t_end = 0.012,
                dt = 1e-4, method = :rodas4p))
            @test r.ok && r.report["algebraic"] == 1
            src = joinpath(dir, "sources")
            write(joinpath(dir, "driver.c"), _EX_DRIVER_X)
            exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
            @test success(`$cc -std=c99 -O2 -I $src $(joinpath(dir, "driver.c")) $(joinpath(src, "model.c")) $(joinpath(src, "bg_solver.c")) -o $exe -lm`)
            x = parse.(Float64, split(strip(read(`$exe 120`, String))))
            low = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.012)
            sol = BGSim.ModelingToolkit.SciMLBase.solve(low.problem,
                BGSim.OrdinaryDiffEqRosenbrock.Rodas5P(); reltol = 1e-11, abstol = 1e-13,
                tstops = [0.01])
            xr = sol(0.012)
            @test maximum(abs.(x .- xr) ./ abs.(xr)) < 1e-6
        end

        @testset "FIX-M2-3's sampled DAE plant in C" begin
            dir = mktempdir()
            r = _EX.export_model(_ex_flat(_ex_dae_sampled_model()), dir;
                settings = _EX.ExportSettings(t_end = 2.0, expose_all = true))
            @test r.ok && _EX.is_rosenbrock(Symbol(r.report["method"]))
            @test r.report["algebraic"] == 1 && r.report["partitions"] == 1
            src = joinpath(dir, "sources")
            write(joinpath(dir, "driver.c"), _EX_DRIVER)
            exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $(joinpath(dir, "driver.c")) $(joinpath(src, "model.c")) $(joinpath(src, "bg_solver.c")) -o $exe -lm`)
            names = vcat([o["name"] for o in r.report["outputs"]], r.report["locals"])
            at(t) = Dict(zip(names, parse.(Float64, split(strip(read(`$exe $(round(Int, t / r.report["dt"]))`, String))))))
            a1 = 2.0 * (1.0 - exp(-0.5))
            v1, v2 = at(1.0), at(2.0)
            @test v1["P1/x"] ≈ a1 atol = 1e-5
            @test v1["S1/u"] == 1.0                    # the 1.0 s tick has run
            b1 = v1["P1/b"]                            # ... and re-solved b at once
            @test b1^3 + b1 ≈ v1["P1/x"] + 2.0 atol = 1e-9
            @test v2["P1/x"] ≈ 4.0 - (4.0 - a1) * exp(-0.5) atol = 1e-5
            b = v2["P1/b"]
            @test b^3 + b ≈ v2["P1/x"] + 2.0 atol = 1e-6   # b re-solved after the tick
        end
    end
end
