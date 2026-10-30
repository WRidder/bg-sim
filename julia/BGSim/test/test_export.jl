# Work package J-EX1: the C/FMU export (plan/EXPORT_PLAN.md).
#
# The acceptance of the work package on small models through the real pipeline:
#   * the interface is exactly the Export markers (input, output) plus the tunable
#     parameters, with their declared ranges; every other parameter is folded;
#   * the step comes from the spectrum, including the declared range of a tunable parameter
#     the Jacobian depends on (D-EX16): a first-order lag with tau in [1 ms, 1 s] has
#     |λ| up to 1000 1/s, so RK4 at 0.3 accuracy needs 4 substeps per 1 ms;
#   * refusals name the construct: a mass-matrix DAE (E111), no markers (W209), a tunable
#     parameter without a range (W210), a forced unstable step (W207), a `dt` that does not
#     divide the communication step or a discrete period or offset (E104, at the clock's block);
#   * `@events` with `reinit` export (J-EX6) with W203 at each event's block and source range,
#     as do the frozen `ifelse` conditions of the hard stop (W203 at its block);
#   * when a C compiler is on PATH, the generated sources compile with -Werror, the hot path
#     does not allocate after instantiate, and the FMU's answer matches the analytic one. The
#     bouncing ball and the relay run in C and match the fixed-step semantics exactly: an
#     event fires at the end of the step in which its condition crosses zero upward.

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
_ex_diags(r, code) = [d for d in r.diagnostics if d.code == code]

# The bouncing ball of examples/bouncing-ball (library/Ball.jl), inline.
const _EX_BALL = """
@block Ball begin
    @parameters begin
        g::Real = 9.81
        e::Real = 0.8
    end
    @variables begin
        h::Real = 1.0
        v::Real = 0.0
    end
    @outputs height::Real
    @equations begin
        ddt(h) ~ v
        ddt(v) ~ -g
        height ~ h
    end
    @events begin
        h < 0 => begin
            reinit(v, -e * v)
        end
    end
end
"""

_ex_ball_model() = bg_model("ExportBall", Any[bg_node("n1", "Ball1", _ex_inline(_EX_BALL))],
    Any[]; t_end = 3.5, points = 351)

# The relay golden (test/golden/continuous/test_Relay.jl): u = 2 sin(2 pi t), hi = 0.5,
# lo = -0.5, two events on one held state.
function _ex_relay_model()
    w = 2.0 * pi
    return bg_model("ExportRelay", Any[
            bg_node("n1", "S1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "2.0", "frequency" => string(w),
                    "phase" => "0.0", "offset" => "0.0")),
            bg_node("n2", "R1", bg_ref("stdlib:continuous/Relay");
                params = Dict{String,Any}("hi" => "0.5", "lo" => "-0.5",
                    "on_value" => "1.0", "off_value" => "0.0", "leak" => "0.0"))],
        Any[bg_conn("c1", "signal", "n1", "y", "n2", "u")]; t_end = 1.2, points = 121)
end

# The hard-stop golden (test/golden/translation/test_HardStop.jl): the imposed velocity v
# drives the relative displacement x = v t through the upper limit at t = 0.0852 s.
function _ex_hard_stop_model(v)
    return bg_model("ExportHardStop", Any[
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => string(v))),
            bg_node("n3", "HS1", bg_ref("stdlib:translation/HardStop");
                params = Dict{String,Any}("lower" => "-0.0213", "upper" => "0.0213",
                    "k" => "5.0e4", "d" => "200.0")),
            bg_node("n4", "F1", bg_ref("stdlib:translation/Fixed"))],
        Any[bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a")]; t_end = 0.2, points = 201)
end

# The same hard stop with a 1 kg mass pushed into it by a constant force: the contact force
# now drives the mass, so the switching conditions reach the derivatives.
function _ex_hard_stop_mass_model()
    return bg_model("ExportHardStopMass", Any[
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "F1", bg_ref("stdlib:translation/ForceSource");
                params = Dict{String,Any}("F" => "10.0")),
            bg_node("n3", "HS1", bg_ref("stdlib:translation/HardStop");
                params = Dict{String,Any}("lower" => "-0.0213", "upper" => "0.0213",
                    "k" => "5.0e4", "d" => "200.0")),
            bg_node("n4", "M1", bg_ref("stdlib:translation/Mass")),
            bg_node("n5", "G1", bg_ref("stdlib:translation/Fixed"))],
        Any[bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n2", "a", "n4", "a"),
            bg_conn("c4", "wire", "n2", "b", "n5", "a"),
            bg_conn("c5", "wire", "n3", "b", "n5", "a"),
            bg_conn("c6", "wire", "n4", "b", "n5", "a")]; t_end = 0.2, points = 201)
end

# A discrete counter next to the lag, for E104 against dt.
function _ex_clock_model(clock)
    counter = """
    @block Count begin
        @outputs n::Real = 0.0
        @discrete $clock begin
            n = n + 1
        end
    end
    """
    return bg_model("ExportClock", Any[
            bg_node("n1", "C", bg_ref("stdlib:sources/Constant")),
            bg_node("n2", "Plant", _ex_inline(_EX_LAG)),
            bg_node("n3", "Tick", _ex_inline(counter))],
        Any[bg_conn("c1", "signal", "n1", "y", "n2", "u")]; t_end = 0.1, points = 11)
end

# Runs the generated C API (bg_reset, then bg_step) for `n` internal steps and prints one row
# per step: t, every state, every output/local.
const _EX_RUNNER = raw"""
#include <stdio.h>
#include <stdlib.h>
#include "model.h"
static bg_model m;
int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 100;
    bg_reset(&m, 0.0);
    for (long k = 0; k <= n; ++k) {
        if (k > 0 && bg_step(&m) != 0) return 2;
        bg_update_outputs(&m);
        printf("%.17g", m.t);
        for (int i = 0; i < BG_NX; ++i) printf(" %.17g", m.x[i]);
        for (int i = 0; i < BG_NY; ++i) printf(" %.17g", m.y[i]);
        printf("\n");
    }
    return 0;
}
"""

"""Compile the export in `dir` with the runner and run it: (rows, state names, y names)."""
function _ex_run_c(cc, dir, report, n)
    src = joinpath(dir, "sources")
    runner = joinpath(dir, "runner.c")
    write(runner, _EX_RUNNER)
    exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
    files = [joinpath(src, f) for f in ("model.c", "bg_solver.c")]
    run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $runner -o $exe -lm`)
    rows = [parse.(Float64, split(l)) for l in eachline(`$exe $n`)]
    model_c = read(joinpath(src, "model.c"), String)
    xnames = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
    ynames = vcat([o["name"] for o in report["outputs"]], String.(report["locals"]))
    return permutedims(reduce(hcat, rows)), xnames, ynames
end

"""The bouncing ball under the export's fixed-step semantics, in Julia: exact parabolas per
step (RK4 is exact on them), the event checked at the end of each step."""
function _ex_ball_fixed_step(n, dt; h = 1.0, v = 0.0, g = 9.81, e = 0.8)
    bounces = Int[]
    for k in 1:n
        z0 = -h
        h, v = h + v * dt - 0.5 * g * dt^2, v - g * dt
        if z0 < 0 && -h >= 0
            v = -e * v
            push!(bounces, k)
        end
    end
    return h, v, bounces
end

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
        @test r.ok && r.report["events"] == 1
        w = _ex_diags(r, "W203")
        @test length(w) == 1 && w[1].path == "Plant" && w[1].source !== nothing

        dae = replace(_EX_LAG, "        y ~ x\n" => "        y^3 + y ~ x\n")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = dae)), mktempdir())
        @test !r.ok && "E111" in _ex_codes(r)
    end

    @testset "E104 against dt, for every period and offset" begin
        e104(clock, dt) = (r = _EX.export_model(_ex_flat(_ex_clock_model(clock)), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.1, dt = dt)); (r, _ex_diags(r, "E104")))
        r, d = e104("Ts = 2e-3", 1e-3)
        @test r.ok && isempty(d)
        # A 1.5 ms period: the base step is 0.5 ms, so a forced 1 ms step misses every
        # second tick.
        r, d = e104("Ts = 1.5e-3", 1e-3)
        @test !r.ok && length(d) == 1
        @test d[1].path == "Tick" && occursin("period 0.0015 s", d[1].message)
        # A 0.5 ms offset on a 2 ms period: the offset alone rules out 1 ms.
        r, d = e104("Ts = 2e-3, [offset = 5e-4]", 1e-3)
        @test !r.ok && length(d) == 1
        @test d[1].path == "Tick" && occursin("offset 0.0005 s", d[1].message)
        r, d = e104("Ts = 2e-3, [offset = 5e-4]", 5e-4)
        @test r.ok && isempty(d)
        # Not a whole number of nanoseconds.
        r, d = e104("Ts = 2e-3", 1e-3 / 3)
        @test !r.ok && length(d) == 1 && occursin("nanoseconds", d[1].message)
        # The automatic step always divides every clock.
        r = _EX.export_model(_ex_flat(_ex_clock_model("Ts = 1.5e-3, [offset = 2.5e-4]")),
            mktempdir(); settings = _EX.ExportSettings(t_end = 0.1))
        @test r.ok && round(Int, 2.5e5) % round(Int, r.report["dt"] * 1e9) == 0
    end

    @testset "events: W203 per site, refusals at the event" begin
        r = _EX.export_model(_ex_flat(_ex_ball_model()), mktempdir();
            settings = _EX.ExportSettings(t_end = 3.5, dt = 1e-3))
        @test r.ok && r.report["events"] == 1 && r.report["modes"] == 0
        w = _ex_diags(r, "W203")
        @test length(w) == 1
        @test w[1].path == "Ball1" && w[1].scope == "@events"
        @test w[1].source !== nothing && w[1].source.range.line > 0

        r = _EX.export_model(_ex_flat(_ex_relay_model()), mktempdir();
            settings = _EX.ExportSettings(t_end = 1.2))
        @test r.ok && r.report["events"] == 2
        @test [d.path for d in _ex_diags(r, "W203")] == ["R1", "R1"]

        # The hard stop has no `@events`; its `ifelse` conditions are the switching sites. In
        # the golden the velocity is imposed, so the contact force reaches only outputs, which
        # are evaluated live at the output instant: nothing is frozen, nothing is late.
        r = _EX.export_model(_ex_flat(_ex_hard_stop_model(0.25)), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.2))
        @test r.ok && r.report["events"] == 0 && r.report["modes"] == 0
        @test isempty(_ex_diags(r, "W203"))
        # Pushing a mass into the stop, the force drives the state: both limits are frozen
        # per step, and W203 names the hard stop for each.
        r = _EX.export_model(_ex_flat(_ex_hard_stop_mass_model()), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.2))
        @test r.ok && r.report["events"] == 0 && r.report["modes"] == 2
        w = _ex_diags(r, "W203")
        @test length(w) == 2 && all(d -> d.path == "HS1", w)
        @test all(d -> d.block == "stdlib:translation/HardStop", w)
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

        @testset "bouncing ball in C: reinit at the end of the crossing step" begin
            dir = mktempdir()
            dt = 1e-3
            n = 3500
            r = _EX.export_model(_ex_flat(_ex_ball_model()), dir;
                settings = _EX.ExportSettings(t_end = 3.5, dt = dt, expose_all = true))
            @test r.ok
            src = joinpath(dir, "sources")
            cxx = Sys.which("g++")
            if cxx !== nothing
                for f in ("model.c", "bg_solver.c")
                    @test success(`$cxx -x c++ -std=c++17 -fsyntax-only -Wall -Wextra -Werror -Wno-unused-parameter -I $src $(joinpath(src, f))`)
                end
            end
            rows, xn, yn = _ex_run_c(cc, dir, r.report, n)
            ih = 1 + findfirst(==("Ball1/h"), xn)
            iv = 1 + findfirst(==("Ball1/v"), xn)
            # A bounce is the jump of v from negative to positive across one step.
            fired = [k - 1 for k in 2:size(rows, 1) if rows[k - 1, iv] < 0 && rows[k, iv] > 0]
            h, v, bounces = _ex_ball_fixed_step(n, dt)
            @test length(bounces) >= 5
            @test fired == bounces
            @test isapprox(rows[end, ih], h; atol = 1e-9) && isapprox(rows[end, iv], v; atol = 1e-9)
            # The first impact, sqrt(2 h0 / g), fires within one dt after the analytic instant.
            t1 = sqrt(2 / 9.81)
            @test 0 < bounces[1] * dt - t1 <= dt
            iy = findfirst(==("Ball1/height"), yn)
            @test iy !== nothing && rows[end, 1 + length(xn) + iy] == rows[end, ih]

            # Already true at the start: z = -h = 0.1 > 0 never rises through zero, so the
            # ball falls through the floor, as in the simulator (only an upward crossing fires).
            below = replace(_EX_BALL, "h::Real = 1.0" => "h::Real = -0.1")
            dir = mktempdir()
            r = _EX.export_model(_ex_flat(bg_model("ExportBallBelow",
                Any[bg_node("n1", "Ball1", _ex_inline(below))], Any[]; t_end = 1.0)), dir;
                settings = _EX.ExportSettings(t_end = 1.0, dt = dt))
            rows, xn, _ = _ex_run_c(cc, dir, r.report, 1000)
            iv = 1 + findfirst(==("Ball1/v"), xn)
            @test all(rows[k, iv] <= rows[k - 1, iv] for k in 2:size(rows, 1))
            @test isapprox(rows[end, iv], -9.81; rtol = 1e-12)
        end

        @testset "relay in C: two events on one state, in declaration order" begin
            dir = mktempdir()
            n = 1200
            r = _EX.export_model(_ex_flat(_ex_relay_model()), dir;
                settings = _EX.ExportSettings(t_end = 1.2, dt = 1e-3))
            @test r.ok
            rows, xn, _ = _ex_run_c(cc, dir, r.report, n)
            is_ = 1 + findfirst(==("R1/s"), xn)
            u(k) = 2.0 * sin(2.0 * pi * (Float64(k * 1_000_000) / 1e9))
            s = 0.0
            expected = [s]
            for k in 1:n
                (u(k - 1) - 0.5 < 0 && u(k) - 0.5 >= 0) && (s = 1.0)
                (-0.5 - u(k - 1) < 0 && -0.5 - u(k) >= 0) && (s = 0.0)
                push!(expected, s)
            end
            @test rows[:, is_] == expected
            # Three switches (on, off, on), each at the end of the step that contains the
            # analytic instant: u rises past 0.5, falls past -0.5, rises past 0.5 again.
            switches = [k - 1 for k in 2:size(rows, 1) if rows[k, is_] != rows[k - 1, is_]]
            w = 2.0 * pi
            analytic = [asin(0.25) / w, (pi + asin(0.25)) / w, 1.0 + asin(0.25) / w]
            @test length(switches) == 3
            @test all(0 < switches[i] * 1e-3 - analytic[i] <= 1e-3 for i in 1:3)
        end

        @testset "hard stop in C: frozen conditions, exact contact law at the step ends" begin
            dir = mktempdir()
            v = 0.25
            r = _EX.export_model(_ex_flat(_ex_hard_stop_model(v)), dir;
                settings = _EX.ExportSettings(t_end = 0.2, dt = 1e-4, expose_all = true))
            @test r.ok
            rows, xn, yn = _ex_run_c(cc, dir, r.report, 2000)
            ix = 1 + findfirst(==("HS1/x"), xn)
            ie = 1 + length(xn) + findfirst(==("HS1/a.e"), yn)
            t = rows[:, 1]
            @test maximum(abs.(rows[:, ix] .- v .* t)) < 1e-12
            law(x) = x > 0.0213 ? 5.0e4 * (x - 0.0213) + 200.0 * v : 0.0
            @test maximum(abs.(rows[:, ie] .- law.(rows[:, ix]))) < 1e-9
        end
    end
end
