# The linear solve `A \ b` on fixed-size arrays (spec "Built-in function whitelist": `\` via
# fixed-size LU; `src/compile/linsolve.jl`).
#
# Golden: a 3x3 and a 6x6 system with a time-varying matrix inside a model whose equations use
# the solve, checked at every output point against Julia's own `\`, and the integral of the
# solution against a fine quadrature. The matrices are built so that the partial-pivoting row
# changes during the run (a zero and a sign change on the diagonal), and the solve adds no
# switching event. The same 6x6 solve in `@discrete` code, `A \ B` with a matrix right-hand
# side, the literal-folding cases and the E004 diagnostics complete it.

using Test
using BGSim
import BGSim.IR
import BGSim.Flat
import BGSim.Compile
import JSON3
using LinearAlgebra: norm

function _ls_node(id, block; params = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id, "name" => id, "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => block)),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params, "constants" => Dict{String,Any}(), "starts" => Dict{String,Any}(),
    )
end

function _ls_model(name, nodes; t_end = 2.0, points = 41, solver = "auto")
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...], "connections" => Any[],
            "subsystemPorts" => Any[], "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => solver, "reltol" => 1.0e-10,
            "abstol" => 1.0e-12, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
end

_ls_flat(doc) = Compile.flatten(IR.parse_model(doc))
_ls_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _ls_run(doc)
    flat = _ls_flat(doc)
    @test isempty(_ls_errors(flat))
    dir = mktempdir()
    result = simulate(flat; run_dir = dir, run_id = "linsolve-test",
        settings = BGSim.RunSettings(doc["settings"]))
    manifest = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(manifest.time.n)
    raw = read(joinpath(dir, "columns.f64"))
    columns = reshape(reinterpret(Float64, raw), (n, length(manifest.signals) + 1))
    values = Dict{String,Vector{Float64}}(
        String(s.id) => collect(columns[:, j + 1]) for (j, s) in enumerate(manifest.signals)
    )
    return flat, result, collect(columns[:, 1]), values
end

# 3x3: A(t) has a11 = sin(2t) (zero at t = 0, so row 2 or 3 is the first pivot) and rows whose
# first-column magnitudes cross, so the pivot row changes during the run.
# det(A) stays within [3.2, 30.3] on [0, 2], so the solution is smooth.
_ls_A3(t) = [sin(2t) 2.0 1.0; 0.5+cos(t) -1.0 3.0; 0.9*cos(3t) 4.0 -6.0+0.3t]
_ls_b3(t) = [1.0 + t, cos(t), 2.0 - sin(t)]

const _LS_SOLVE3 = """
@block Solve3 begin
    @parameters w::Real = 1.0, [unit = "1/s", description = "Makes the time dimensionless"]
    @outputs begin
        x::Vec{3}
        y::Vec{3}
    end
    @variables begin
        A::Mat{3,3}
        b::Vec{3}
        z::Vec{3} = [0.0, 0.0, 0.0]
        s::Real
    end
    @equations begin
        s ~ w * t
        A ~ [sin(2 * s) 2.0 1.0; 0.5 + cos(s) -1.0 3.0; 0.9 * cos(3 * s) 4.0 -6.0 + 0.3 * s]
        b ~ [1.0 + s, cos(s), 2.0 - sin(s)]
        x ~ A \\ b
        ddt(z) ~ x
        y ~ z
    end
end
"""

# 6x6: an anti-diagonal-dominant matrix whose diagonal entries oscillate through zero, so
# pivoting is required, plus a parameter in the matrix (a run-time value, not folded).
function _ls_A6(t, p)
    A = zeros(6, 6)
    for i in 1:6, j in 1:6
        A[i, j] = 0.1 * ((i * j) % 5) - 0.2
    end
    for i in 1:6
        A[i, 7 - i] += 3.0 + p * i
        A[i, i] += 2.0 * sin(t + i)
    end
    A[1, 2] += cos(t)
    A[6, 1] -= t
    return A
end
_ls_b6(t) = [sin(t + k) + 0.1k for k in 1:6]

function _ls_solve6_source(; discrete::Bool)
    io = IOBuffer()
    println(io, "@block Solve6$(discrete ? "D" : "") begin")
    println(io, "    @parameters begin")
    println(io, "        p::Real = 0.25")
    println(io, "        w::Real = 1.0, [unit = \"1/s\"]")
    println(io, "    end")
    println(io, "    @outputs x::Vec{6}")
    println(io, "    @variables begin")
    println(io, "        A::Mat{6,6}")
    println(io, "        b::Vec{6}")
    println(io, discrete ? "        k::Real = 0.0" : "        s::Real")
    println(io, "    end")
    if discrete
        println(io, "    @discrete Ts = 0.05 begin")
        println(io, "        k = k + 1")
        println(io, "        tk = k * 0.05")
        tv = "tk"
        eq = "="
    else
        println(io, "    @equations begin")
        println(io, "        s ~ w * t")
        tv = "s"
        eq = "~"
    end
    for i in 1:6, j in 1:6
        base = 0.1 * ((i * j) % 5) - 0.2
        term = string(base)
        j == 7 - i && (term *= " + 3.0 + p * $i")
        j == i && (term *= " + 2.0 * sin($tv + $i)")
        (i, j) == (1, 2) && (term *= " + cos($tv)")
        (i, j) == (6, 1) && (term *= " - $tv")
        println(io, "        A[$i, $j] $eq $term")
    end
    for k in 1:6
        println(io, "        b[$k] $eq sin($tv + $k) + 0.1 * $k")
    end
    println(io, "        x $eq A \\ b")
    println(io, "    end")
    println(io, "end")
    return String(take!(io))
end

@testset "linear solve A \\ b (fixed-size LU, partial pivoting)" begin
    @testset "3x3 in @equations, time-varying, against Julia's \\ and the integral" begin
        doc = _ls_model("ls3", [_ls_node("S", _LS_SOLVE3)]; t_end = 2.0, points = 41)
        flat, result, time, values = _ls_run(doc)
        @test result.status == "done"
        @test length(time) >= 41
        # the solve adds no switching event: no nonsmooth condition at all in this model
        @test isempty(BGSim.nonsmooth_conditions(flat))
        # hidden unknowns are not recorded signals
        @test !any(k -> occursin("__lu", k), keys(values))
        worst = 0.0
        for (r, t) in enumerate(time)
            x = _ls_A3(t) \ _ls_b3(t)
            for i in 1:3
                worst = max(worst, abs(values["S/x[$i]"][r] - x[i]) / max(1.0, abs(x[i])))
            end
        end
        @test worst < 1.0e-12
        # the pivot row really changes during the run (|a11| vs |a21| vs |a31|)
        piv(t) = argmax(abs.(_ls_A3(t)[:, 1]))
        @test length(unique(piv.(time))) >= 2
        # integral of the solution (trapezoid on a fine grid)
        ts = range(0.0, 2.0; length = 20001)
        xs = [(_ls_A3(t) \ _ls_b3(t)) for t in ts]
        integral = sum((xs[k] + xs[k + 1]) / 2 * step(ts) for k in 1:(length(ts) - 1))
        for i in 1:3
            @test isapprox(values["S/y[$i]"][end], integral[i]; rtol = 1.0e-7, atol = 1.0e-8)
        end
    end

    @testset "6x6 in @equations with a zero diagonal and a parameter" begin
        p = 0.25
        doc = _ls_model("ls6", [_ls_node("S6", _ls_solve6_source(discrete = false);
            params = Dict{String,Any}("p" => string(p)))]; t_end = 3.0, points = 31)
        flat, result, time, values = _ls_run(doc)
        @test isempty(BGSim.nonsmooth_conditions(flat))
        worst = 0.0
        for (r, t) in enumerate(time)
            x = _ls_A6(t, p) \ _ls_b6(t)
            for i in 1:6
                worst = max(worst, abs(values["S6/x[$i]"][r] - x[i]) / max(1.0, abs(x[i])))
            end
        end
        @test worst < 1.0e-11
        # the setup needs pivoting: the first pivot is not on the diagonal
        @test argmax(abs.(_ls_A6(0.0, p)[:, 1])) != 1
        # a run-time parameter change reuses the compiled model and still solves exactly
        p2 = -0.4
        doc2 = _ls_model("ls6", [_ls_node("S6", _ls_solve6_source(discrete = false);
            params = Dict{String,Any}("p" => string(p2)))]; t_end = 3.0, points = 31)
        _, _, time2, values2 = _ls_run(doc2)
        worst2 = maximum(abs(values2["S6/x[$i]"][r] - (_ls_A6(t, p2) \ _ls_b6(t))[i])
                         for (r, t) in enumerate(time2) for i in 1:6)
        @test worst2 < 1.0e-10
    end

    @testset "6x6 in @discrete" begin
        p = 0.25
        doc = _ls_model("ls6d", [_ls_node("D6", _ls_solve6_source(discrete = true);
            params = Dict{String,Any}("p" => string(p)))]; t_end = 1.0, points = 21)
        flat, result, time, values = _ls_run(doc)
        # the value held after tick k (t = 0.05 k) is the solve at tk = 0.05 k
        for (r, t) in enumerate(time)
            k = round(Int, t / 0.05)
            (k >= 1 && isapprox(t, 0.05k; atol = 1e-12)) || continue
            r == length(time) || time[r + 1] != t || continue   # the right-hand row
            x = _ls_A6(0.05k, p) \ _ls_b6(0.05k)
            for i in 1:6
                @test isapprox(values["D6/x[$i]"][r], x[i]; rtol = 1.0e-12, atol = 1.0e-13)
            end
        end
    end

    @testset "the manual's damped least-squares step in @discrete" begin
        src = """
        @block DLS begin
            @parameters lam::Real = 0.01
            @outputs dq::Vec{4}
            @variables begin
                J::Mat{3,4}
                e::Vec{3}
                k::Real = 0.0
            end
            @discrete Ts = 0.1 begin
                k = k + 1
                J = [1.0 0.5 * k 0.0 0.2; 0.0 1.0 0.3 0.0; 0.1 0.0 1.0 k]
                e = [1.0, -0.5, 0.25 * k]
                JJt = J * transpose(J) + lam * [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0]
                dq = transpose(J) * (JJt \\ e)
            end
        end
        """
        doc = _ls_model("lsdls", [_ls_node("I", src)]; t_end = 0.5, points = 6)
        _, _, time, values = _ls_run(doc)
        k = 5
        J = [1.0 0.5k 0.0 0.2; 0.0 1.0 0.3 0.0; 0.1 0.0 1.0 k]
        e = [1.0, -0.5, 0.25k]
        dq = transpose(J) * ((J * transpose(J) + 0.01 * [1.0 0 0; 0 1.0 0; 0 0 1.0]) \ e)
        for i in 1:4
            @test isapprox(values["I/dq[$i]"][end], dq[i]; rtol = 1.0e-12, atol = 1.0e-14)
        end
    end

    @testset "A \\ B with a matrix right-hand side; transpose(A) \\ b" begin
        src = """
        @block SolveMat begin
            @parameters w::Real = 1.0, [unit = "1/s"]
            @outputs begin
                X::Mat{2,2}
                y::Vec{2}
            end
            @variables begin
                A::Mat{2,2}
                s::Real
            end
            @equations begin
                s ~ w * t
                A ~ [cos(s) 2.0; 1.0 + s sin(s)]
                X ~ A \\ [1.0 2.0; 3.0 4.0]
                y ~ transpose(A) \\ [1.0, -1.0]
            end
        end
        """
        doc = _ls_model("lsmat", [_ls_node("M", src)]; t_end = 1.0, points = 11)
        flat, result, time, values = _ls_run(doc)
        A(t) = [cos(t) 2.0; 1.0+t sin(t)]
        worst = 0.0
        for (r, t) in enumerate(time)
            X = A(t) \ [1.0 2.0; 3.0 4.0]
            y = transpose(A(t)) \ [1.0, -1.0]
            worst = max(worst, abs(values["M/X[1,1]"][r] - X[1, 1]), abs(values["M/X[2,2]"][r] - X[2, 2]),
                abs(values["M/X[1,2]"][r] - X[1, 2]), abs(values["M/y[2]"][r] - y[2]))
        end
        @test worst < 1.0e-12
    end

    @testset "literal folding and structure" begin
        src = """
        @block SolveLit begin
            @parameters a::Real = 2.0
            @outputs begin
                x::Vec{2}
                u::Vec{3}
            end
            @equations begin
                x ~ [0.0 1.0; 4.0 0.0] \\ [2.0, 8.0]
                u ~ [a 1.0 0.0; 0.0 a 1.0; 0.0 0.0 a] \\ [1.0 + a, 1.0 + a, a]
            end
        end
        """
        flat = _ls_flat(_ls_model("lslit", [_ls_node("L", src)]))
        @test isempty(_ls_errors(flat))
        eqs = Dict(sprint(show, e.lhs) => e.rhs for e in flat.equations)
        # an all-literal system is solved at compile time
        lit = [e for e in flat.equations if e.lhs isa BGSim.Name && e.lhs.name === Symbol("L/x[1]")]
        @test length(lit) == 1 && lit[1].rhs isa BGSim.Lit && lit[1].rhs.value == 2.0
        # a structurally upper-triangular matrix needs no pivot choice: no `ifelse` at all
        @test !any(e -> occursin("ifelse", sprint(show, e.rhs)), flat.equations)
        flat_run, _, time, values = _ls_run(_ls_model("lslit", [_ls_node("L", src)]; t_end = 0.1, points = 2))
        @test values["L/u[1]"][end] ≈ 1.0
        @test values["L/u[2]"][end] ≈ 1.0
        @test values["L/u[3]"][end] ≈ 1.0
    end

    @testset "diagnostics" begin
        nonsquare = """
        @block BadSolve begin
            @outputs x::Vec{2}
            @variables A::Mat{2,3}
            @equations begin
                A ~ [1.0 2.0 3.0; 4.0 5.0 t]
                x ~ A \\ [1.0, 2.0]
            end
        end
        """
        pb = BGSim.parse_block(nonsquare)
        ds = BGSim.check_block(pb)
        @test any(d -> d.code == "E004" && occursin("square", d.message), ds)
        mismatch = """
        @block BadSolve2 begin
            @outputs x::Vec{2}
            @variables A::Mat{2,2}
            @equations begin
                A ~ [1.0 2.0; 4.0 t]
                x ~ A \\ [1.0, 2.0, 3.0]
            end
        end
        """
        ds = BGSim.check_block(BGSim.parse_block(mismatch))
        @test any(d -> d.code == "E004" && occursin("sizes do not match", d.message), ds)
        singular = """
        @block SingularSolve begin
            @outputs x::Vec{2}
            @equations begin
                x ~ [t 0.0; 1.0 0.0] \\ [1.0, 2.0]
            end
        end
        """
        flat = _ls_flat(_ls_model("lssing", [_ls_node("Z", singular)]))
        @test any(d -> d.code == "E004" && occursin("singular", d.message), flat.diagnostics)
        # the constant folder solves too (a parameter default)
        folded = BGSim.parse_block("""
        @block FoldSolve begin
            @constants c::Vec{2} = [2.0 0.0; 0.0 4.0] \\ [2.0, 2.0]
            @outputs y::Real
            @equations y ~ c[1] + c[2]
        end
        """)
        @test BGSim.constant_env(folded)[:c] == [1.0, 0.5]
    end
end
