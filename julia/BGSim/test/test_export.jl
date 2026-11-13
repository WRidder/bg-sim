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

    @testset "a pass-through input (ExportInputPass) exports as an ExportInput (X-EX1)" begin
        # In simulation the wired Constant (3.0) reaches the plant; in the export the host
        # does, starting at the marker's value (2.0), exactly as with an ExportInput.
        doc = _ex_lag_model()
        for n in doc["diagram"]["nodes"]
            n["name"] == "U" && (n["block"] = bg_ref("stdlib:converters/ExportInputPass"))
        end
        push!(doc["diagram"]["nodes"], bg_node("n4", "C", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "3.0")))
        push!(doc["diagram"]["connections"], bg_conn("c3", "signal", "n4", "y", "n1", "u"))
        flat = _ex_flat(doc)
        @test isempty([d for d in flat.diagnostics if d.severity == "error"])
        pass_dir, plain_dir = mktempdir(), mktempdir()
        settings = _EX.ExportSettings(t_end = 0.1)
        rp = _EX.export_model(flat, pass_dir; settings)
        rq = _EX.export_model(_ex_flat(_ex_lag_model()), plain_dir; settings)
        @test rp.ok && rq.ok
        @test rp.report["inputs"] == [Dict("name" => "U", "id" => "U/value", "start" => 2.0)]
        @test [o["name"] for o in rp.report["outputs"]] == ["Y"]
        @test [p["name"] for p in rp.report["parameters"]] == ["Plant/tau"]
        @test rp.report["dt"] == rq.report["dt"] && rp.report["method"] == rq.report["method"]
        model_c = read(joinpath(pass_dir, "sources", "model.c"), String)
        @test occursin("m->u[0]", model_c)
        xml = read(joinpath(pass_dir, "modelDescription.xml"), String)
        @test occursin("name=\"U\" valueReference=\"2\" causality=\"input\"", xml)
        # The job's reference sees the same: the transformed flat, not the Constant.
        @test _EX.host_inputs(flat) !== flat
        @test _EX.input_markers(flat) == ["U"]
    end

    @testset "sticky notes (diagram.annotations) change nothing in the export" begin
        plain_doc = _ex_lag_model()
        noted_doc = _ex_lag_model()
        noted_doc["diagram"]["annotations"] = Any[
            Dict{String,Any}("id" => "note1", "kind" => "text", "text" => "**Lag** under test",
                "x" => 0.0, "y" => -100.0, "w" => 200.0, "h" => 100.0),
            Dict{String,Any}("id" => "note2", "kind" => "text", "text" => "- one\n- two",
                "x" => 240.0, "y" => -100.0, "w" => 160.0, "h" => 80.0, "color" => "pink"),
        ]
        plain_dir, noted_dir = mktempdir(), mktempdir()
        settings = _EX.ExportSettings(t_end = 0.1)
        rp = _EX.export_model(_ex_flat(plain_doc), plain_dir; settings)
        rn = _EX.export_model(_ex_flat(noted_doc), noted_dir; settings)
        @test rp.ok && rn.ok
        @test _ex_codes(rp) == _ex_codes(rn)
        @test [i["name"] for i in rn.report["inputs"]] == [i["name"] for i in rp.report["inputs"]]
        @test [o["name"] for o in rn.report["outputs"]] == [o["name"] for o in rp.report["outputs"]]
        @test read(joinpath(noted_dir, "sources", "model.c"), String) ==
              read(joinpath(plain_dir, "sources", "model.c"), String)
    end

    @testset "canvas shapes (diagram.shapes) change nothing in the export" begin
        plain_doc = _ex_lag_model()
        shaped_doc = _ex_lag_model()
        shaped_doc["diagram"]["shapes"] = Any[
            Dict{String,Any}("id" => "s1", "kind" => "roundedRectangle", "x" => -40.0,
                "y" => -40.0, "w" => 400.0, "h" => 240.0, "fill" => "blue", "opacity" => 0.5,
                "text" => "Lag", "locked" => true),
            Dict{String,Any}("id" => "s2", "kind" => "arrow", "x" => 0.0, "y" => 260.0,
                "w" => 200.0, "h" => -60.0, "stroke" => "pink", "strokeStyle" => "dashed"),
        ]
        plain_dir, shaped_dir = mktempdir(), mktempdir()
        settings = _EX.ExportSettings(t_end = 0.1)
        rp = _EX.export_model(_ex_flat(plain_doc), plain_dir; settings)
        rs = _EX.export_model(_ex_flat(shaped_doc), shaped_dir; settings)
        @test rp.ok && rs.ok
        @test _ex_codes(rp) == _ex_codes(rs)
        @test [i["name"] for i in rs.report["inputs"]] == [i["name"] for i in rp.report["inputs"]]
        @test [o["name"] for o in rs.report["outputs"]] == [o["name"] for o in rp.report["outputs"]]
        @test read(joinpath(shaped_dir, "sources", "model.c"), String) ==
              read(joinpath(plain_dir, "sources", "model.c"), String)
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

        # A DAE: RK4 refuses it (E111), auto picks a Rosenbrock method (J-EX3).
        dae = replace(_EX_LAG, "        y ~ x\n" => "        y^3 + y ~ x\n")
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = dae)), mktempdir();
            settings = _EX.ExportSettings(method = :rk4))
        @test !r.ok && "E111" in _ex_codes(r)
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = dae)), mktempdir())
        @test r.ok && r.report["method"] in ("ros2", "ros34pw2", "rodas4p")
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
        # A well-posed algebraic block over 16 decades (cond 1e16 as it stands) is index 1:
        # x' = -x + z1 + z2, 0 = x - 1e-8 z1, 0 = x - 1e8 z2  ->  λ = -1 + 1e8 + 1e-8.
        Jw = [-1.0 1.0 1.0; 1.0 -1e-8 0.0; 1.0 0.0 -1e8]
        @test LinearAlgebra.cond(Jw[2:3, 2:3], 1) > 1e14
        @test real(only(_EX.pencil_eigvals(Jw, [1.0, 0.0, 0.0]))) ≈ -1 + 1e8 + 1e-8
        @test _EX.equilibrated_cond([1.0 0.0; 0.0 0.0]) == Inf
        # E111 guard: a row (or column) that is zero up to finite-difference noise is zero. The
        # scaling alone would blow the 1e-13 noise up to a regular row (cond about 1e2).
        A6 = [4.0 1 0 0 0 1; 1 5 1 0 0 0; 0 1 6 1 0 0; 0 0 1 7 1 0; 1 0 0 1 8 1; 0 0 0 0 0 0]
        noisy = copy(A6)
        noisy[6, :] = 1e-13 .* [0.3, -0.7, 0.5, 0.9, -0.2, 0.6]
        @test _EX.equilibrated_cond(noisy; floor = 0.0) < 1e4   # what the guard prevents
        @test _EX.equilibrated_cond(noisy) == Inf
        @test _EX.equilibrated_cond(collect(noisy')) == Inf      # the same as a column
        # the floor of a row scales with its terms: 1e-10 noise in a 1e3 block, per-row floor
        big = 1e3 .* A6
        big[6, :] = 1e-10 .* [0.3, -0.7, 0.5, 0.9, -0.2, 0.6]
        @test _EX.equilibrated_cond(big; floor = _EX.FD_NOISE_FLOOR .* 1e3) == Inf
        # well posed, rows over 16 decades: every row has an entry above the floor
        @test isfinite(_EX.equilibrated_cond([1.0 0.5 0; 0 1e-8 2e-8; 3e8 0 1e8]))
        # the pencil: the noisy algebraic row of x' = -x + z1, 0 = x - z1 + noise*z2,
        # 0 = 1e-13 (x + z1 + z2) is singular, not index 1
        Jn = [-1.0 1.0 0.0; 1.0 -1.0 1e-13; 1e-13 1e-13 1e-13]
        @test LinearAlgebra.issuccess(LinearAlgebra.lu(Jn[2:3, 2:3]; check = false))
        @test_throws LinearAlgebra.SingularException _EX.pencil_eigvals(Jn, [1.0, 0.0, 0.0])
        # ... and the 16-decade block of `Jw` above stays index 1
        @test length(_EX.pencil_eigvals(Jw, [1.0, 0.0, 0.0])) == 1
    end

    @testset "stiff undamped modes are damped numerically (D-EX7, W213)" begin
        tol = _EX.mode_tolerance(0.3)
        # An undamped mode (z on the imaginary axis): accepted only when the method damps it
        # and it is stiff relative to the step.
        @test _EX.mode_class(:rodas4p, 1000im, tol, 0.05, 10.0) === :numerical  # |R| = 0.009
        @test _EX.mode_class(:rodas4p, 100im, tol, 0.05, 10.0) === :fail        # |R| = 0.093
        @test _EX.mode_class(:ros2, 12im, tol, 0.1, 10.0) === :numerical        # |R| = 0.069
        @test _EX.mode_class(:ros2, 12im, tol, 0.1, 20.0) === :fail             # |z| below the threshold
        @test _EX.mode_class(:rodas4p, -1e4, tol, 0.05, 10.0) === :damped
        @test _EX.mode_class(:rodas4p, -0.01 + 0.0im, tol, 0.05, 10.0) === :resolved
        # A 1e6 rad/s joint stiffness next to a slow lag: one Rodas4P step per millisecond,
        # one mode at 159 kHz damped numerically.
        ms = Int64(1_000_000)
        joint = [(0.0, ComplexF64[1e6im, -1e6im, -20.0])]
        c = _EX.choose_step(:rodas4p, joint, ms)
        @test c.substeps == 1 && !c.over_budget
        @test _EX.step_rule_met(:rodas4p, joint, 1e-3)
        n, f = _EX.numerically_damped(:rodas4p, joint, 1e-3)
        @test n == 1 && isapprox(f, 1e6 / 2π; rtol = 1e-9)
        # The threshold: with stiff_ratio above h·|λ| the mode must be resolved again.
        c = _EX.choose_step(:rodas4p, joint, ms; stiff_ratio = 2000.0)
        @test c.substeps > 1 && !_EX.step_rule_met(:rodas4p, joint, 1e-3; stiff_ratio = 2000.0)
        @test _EX.numerically_damped(:rodas4p, joint, c.dt_ns / 1e9; stiff_ratio = 2000.0)[1] == 0
        # An undamped mode in the bandwidth (a 1 kHz LC circuit, h·|λ| = 6.3 at 1 ms) is still
        # resolved by Rodas4P: more substeps, nothing damped numerically.
        lc = [(0.0, ComplexF64[2π * 1000im, -2π * 1000im])]
        c = _EX.choose_step(:rodas4p, lc, ms)
        @test c.substeps > 1 && !c.over_budget
        @test !_EX.step_rule_met(:rodas4p, lc, 1e-3)
        @test abs(2π * 1000 * c.dt_ns / 1e9) < 1
        @test _EX.numerically_damped(:rodas4p, lc, c.dt_ns / 1e9) == (0, Inf)
        # RK4 is unchanged: it resolves the joint, whatever stiff_ratio says.
        for sr in (10.0, 1e9)
            c = _EX.choose_step(:rk4, joint, ms; stiff_ratio = sr)
            @test c.dt_ns / 1e9 <= 0.3 / 1e6 && c.over_budget
            @test !_EX.step_rule_met(:rk4, joint, 1e-3; stiff_ratio = sr)
        end
        @test _EX.numerically_damped(:rk4, joint, 1e-3) == (0, Inf)
        # ROS2 (not stiffly accurate) is never suggested when it damps a mode numerically,
        # even when it is the cheapest; forced, it is kept.
        best, table = _EX.choose_method(_EX.ROSENBROCK_METHODS, joint, ms, 3;
            f_ops = 30, jac_ops = m -> 20.0)
        r2 = only(r for r in table if r.method === :ros2)
        @test r2.numerical == 1 && !r2.choice.over_budget
        @test r2.cost < minimum(r.cost for r in table if r.method !== :ros2)
        @test best.method !== :ros2 && !best.over_budget
        best, _ = _EX.choose_method((:ros2,), joint, ms, 3; f_ops = 30, jac_ops = m -> 20.0)
        @test best.method === :ros2

        # In the export: W213 and the report entry.
        stiff_lag = """
        @block StiffLag begin
            @inputs u::Real
            @outputs y::Real
            @parameters tau::Real = 0.05
            @parameters w0::Real = 1.0e6
            @variables x::Real = 0.0
            @variables q::Real = 0.0
            @variables p::Real = 0.0
            @equations begin
                ddt(x) ~ (u - x) / tau
                ddt(q) ~ p
                ddt(p) ~ -w0^2 * q + x
                y ~ x + q
            end
        end
        """
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = stiff_lag)), mktempdir();
            settings = _EX.ExportSettings(method = :rodas4p, t_end = 0.1))
        @test r.ok && r.report["method"] == "rodas4p" && r.report["dt"] == 1e-3
        w = _ex_diags(r, "W213")
        @test length(w) == 1 && occursin("1 stiff undamped mode at or above 159000 Hz", w[1].message)
        @test occursin("RODAS4P", w[1].message) && occursin("force rk4", w[1].message)
        nd = r.report["spectrum"]["numericallyDamped"]
        @test nd["modes"] == 1 && isapprox(nd["minHz"], 1e6 / 2π; rtol = 1e-6)
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = stiff_lag)), mktempdir();
            settings = _EX.ExportSettings(method = :rk4, t_end = 0.1))
        @test r.ok && isempty(_ex_diags(r, "W213"))
        @test r.report["spectrum"]["numericallyDamped"]["modes"] == 0
    end

    @testset "over-budget fallback to a relaxed damping (D-EX7, W214)" begin
        @test _EX.ExportSettings(Dict{String,Any}()).damping === nothing
        @test _EX.ExportSettings(Dict("damping" => 0.05)).damping == 0.05
        # Five lags from 1 ms down to 100 ns: every method needs more than 1000 substeps under
        # the strict rule; with damping 0.5 the fast lags may decay unresolved in one step.
        chain = """
        @block LagChain begin
            @inputs u::Real
            @outputs y::Real
            @variables x1::Real = 0.0
            @variables x2::Real = 0.0
            @variables x3::Real = 0.0
            @variables x4::Real = 0.0
            @variables x5::Real = 0.0
            @equations begin
                ddt(x1) ~ (u - x1) / 1.0e-3
                ddt(x2) ~ (u - x2) / 1.0e-4
                ddt(x3) ~ (u - x3) / 1.0e-5
                ddt(x4) ~ (u - x4) / 1.0e-6
                ddt(x5) ~ (u - x5) / 1.0e-7
                y ~ x1 + x2 + x3 + x4 + x5
            end
        end
        """
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = chain)), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.1))
        @test r.ok && _EX.is_rosenbrock(Symbol(r.report["method"])) && r.report["substeps"] == 1
        w = _ex_diags(r, "W214")
        @test length(w) == 1 && isempty(_ex_diags(r, "W207"))
        @test occursin("no method meets the strict step rule within the budget", w[1].message)
        @test occursin("relaxed damping (0.5)", w[1].message) && occursin("force rk4", w[1].message)
        @test r.report["spectrum"]["damping"] == 0.5 && r.report["spectrum"]["relaxedDamping"]
        @test all(s -> s["withinBudget"] || s["method"] == "rk4", r.report["selection"])
        # An explicit damping disables the fallback: the strict rule and W207.
        r = _EX.export_model(_ex_flat(_ex_lag_model(lag = chain)), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.1, damping = 0.05))
        @test r.ok && isempty(_ex_diags(r, "W214")) && !isempty(_ex_diags(r, "W207"))
        @test r.report["spectrum"]["damping"] == 0.05 && !r.report["spectrum"]["relaxedDamping"]
        # A model within the budget is not touched.
        r = _EX.export_model(_ex_flat(_ex_lag_model()), mktempdir();
            settings = _EX.ExportSettings(t_end = 0.1))
        @test r.ok && isempty(_ex_diags(r, "W214")) && !r.report["spectrum"]["relaxedDamping"]
        @test r.report["spectrum"]["damping"] == 0.05
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
                @test r.report["jacobian"]["kind"] == (jac === :fd ? "fd" : "symbolic")
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

        # The dense LU re-solves b by a dense elimination of dg/db; the sparse LU on its
        # static tables (BG_SPARSE_PROJECT, bg_alg_factor).
        @testset "FIX-M2-3's sampled DAE plant in C ($solver)" for solver in (:auto, :sparse)
            dir = mktempdir()
            r = _EX.export_model(_ex_flat(_ex_dae_sampled_model()), dir;
                settings = _EX.ExportSettings(t_end = 2.0, expose_all = true, linear_solver = solver))
            @test r.ok && _EX.is_rosenbrock(Symbol(r.report["method"]))
            @test r.report["algebraic"] == 1 && r.report["partitions"] == 1
            @test r.report["linearAlgebra"]["linearSolver"] == (solver === :sparse ? "sparse" : "dense")
            @test r.report["linearAlgebra"]["projection"]["sparse"] == (solver === :sparse)
            src = joinpath(dir, "sources")
            @test occursin("#define BG_SPARSE_PROJECT", read(joinpath(src, "model.h"), String)) ==
                  (solver === :sparse)
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

        # J-EX6's open point: a reinit on a DAE moves the state, so the algebraic unknown is
        # re-solved at once, as after a tick. a ramps at 1/s and is reset to 0 when it
        # crosses 0.5; right after that step b must solve b^3 + b = a again.
        @testset "reinit on a DAE re-solves the algebraic unknown" begin
            src_block = """
            @block DaeSaw begin
                @outputs x::Real = 0.0
                @variables begin
                    a::Real = 0.0, [state = :prefer]
                    b::Real = 0.0
                end
                @equations begin
                    ddt(a) ~ 1.0
                    b^3 + b ~ a
                    x ~ a
                end
                @events begin
                    a > 0.5 => begin
                        reinit(a, 0.0)
                    end
                end
            end
            """
            model = bg_model("DaeSaw", Any[bg_node("n1", "P1", _ex_inline(src_block))], Any[];
                t_end = 1.0)
            dir = mktempdir()
            r = _EX.export_model(_ex_flat(model), dir;
                settings = _EX.ExportSettings(t_end = 1.0, dt = 1e-3, method = :rodas4p))
            @test r.ok && r.report["algebraic"] == 1 && r.report["events"] == 1
            src = joinpath(dir, "sources")
            write(joinpath(dir, "driver.c"), _EX_DRIVER_X)
            exe = joinpath(dir, Sys.iswindows() ? "driver.exe" : "driver")
            @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $(joinpath(dir, "driver.c")) $(joinpath(src, "model.c")) $(joinpath(src, "bg_solver.c")) -o $exe -lm`)
            xnames = Dict(m.captures[2] => parse(Int, m.captures[1]) + 1 for m in
                eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", read(joinpath(src, "model.c"), String)))
            ia, ib = xnames["P1/a"], xnames["P1/b"]
            state(n) = parse.(Float64, split(strip(read(`$exe $n`, String))))
            k = findfirst(n -> state(n)[ia] < 0.25, 495:510)
            @test k !== nothing
            x = state(494 + k)                        # the first step after the reset
            @test x[ia] < 0.01
            @test abs(x[ib]^3 + x[ib] - x[ia]) < 1e-9
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

        @testset "events on a jump in C: a tick and a host input fire at the jump" begin
            # `k` (held) steps to +1 at the tick t = 0.25 and back to -1 at t = 0.6; the host
            # sets the input u to 1 after step 300 (t = 0.3). The conditions cross zero only
            # across these jumps, never inside a step, so before runtime 0.7.0 no event fired.
            latch = """
            @block JumpLatch begin
                @inputs u::Real
                @variables begin
                    x::Real = 0.0
                    hit::Real = 0.0
                    down::Real = 0.0
                    uin::Real = 0.0
                    k::Real = -1.0
                    n::Real = 0.0
                end
                @discrete Ts = 0.01 begin
                    n = n + 1
                    k = ifelse(n >= 25 && n < 60, 1.0, -1.0)
                end
                @equations begin
                    ddt(x) ~ 1.0
                    ddt(hit) ~ 0.0
                    ddt(down) ~ 0.0
                    ddt(uin) ~ 0.0
                end
                @events begin
                    k > 0 => begin
                        reinit(hit, hit + 1.0)
                    end
                    k < 0 => begin
                        reinit(down, down + 1.0)
                    end
                    u > 0.5 => begin
                        reinit(uin, uin + 1.0)
                    end
                end
            end
            """
            doc = bg_model("ExportJumpLatch", Any[
                    bg_node("n1", "U", bg_ref("stdlib:converters/ExportInput");
                        params = Dict{String,Any}("value" => "0.0")),
                    bg_node("n2", "L", _ex_inline(latch))],
                Any[bg_conn("c1", "signal", "n1", "y", "n2", "u")]; t_end = 1.0, points = 101)
            dir = mktempdir()
            r = _EX.export_model(_ex_flat(doc), dir;
                settings = _EX.ExportSettings(t_end = 1.0, dt = 1e-3))
            @test r.ok && r.report["events"] == 3
            runner = replace(_EX_RUNNER,
                "if (k > 0 && bg_step(&m) != 0) return 2;" =>
                    "if (k == 301) m.u[0] = 1.0;\n        if (k > 0 && bg_step(&m) != 0) return 2;")
            src = joinpath(dir, "sources")
            write(joinpath(dir, "runner.c"), runner)
            exe = joinpath(dir, Sys.iswindows() ? "runner.exe" : "runner")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c")]
            run(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I $src $files $(joinpath(dir, "runner.c")) -o $exe -lm`)
            rows = permutedims(reduce(hcat, [parse.(Float64, split(l)) for l in eachline(`$exe 1000`)]))
            model_c = read(joinpath(src, "model.c"), String)
            xn = [String(m.captures[2]) for m in eachmatch(r"/\* x\[(\d+)\] = (\S+) \*/", model_c)]
            col(name) = rows[:, 1 + findfirst(==(name), xn)]
            step_of(v) = findfirst(>(0.5), v) - 1      # rows are steps 0, 1, 2, ...
            # the tick at the end of step 250 (t = 0.25) fires `hit` in that step; step 600 `down`
            @test step_of(col("L/hit")) == 250 && col("L/hit")[end] == 1.0
            @test step_of(col("L/down")) == 600 && col("L/down")[end] == 1.0
            # the input set before step 301 fires at its start (t = 0.3), seen after that step
            @test step_of(col("L/uin")) == 301 && col("L/uin")[end] == 1.0
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
