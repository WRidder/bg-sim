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

        dae = replace(_EX_LAG, "        y ~ x\n" => "        y^3 + y ~ x\n")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = dae)), mktempdir())
        @test !r.ok && "E111" in _ex_codes(r)
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
    end
end
