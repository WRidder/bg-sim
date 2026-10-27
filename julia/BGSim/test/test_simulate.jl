# Work package J1.5: lowering and simulation (continuous only).
#
# Acceptance of the work package (plan sections 5.8 without events/discrete, 5.10, 5.11 and
# 5.12):
#   * the DC motor fixtures of plan 9.1 meet their checks: steady state
#     omega = k*V/(R*d + k^2) = 239.81 rad/s (rtol 1e-4), and the iconic and bond-graph
#     models agree to better than 1e-6 rad/s once settled;
#   * `columns.f64` round-trips through the row-major `stream.f64` and the manifest, and a
#     known analytic value (the RLC overshoot) matches;
#   * a parameter-only re-run hits the structural cache and reaches first data in under
#     300 ms after one warm-up re-run;
#   * solver failure is E901 with the time and the largest states; cancellation is reported
#     as `cancelled` with the rows written so far; a model with an error diagnostic is
#     refused;
#   * `int`, the nonsmooth rewrites and the `nonsmooth_conditions` seam lower correctly.

using Test
using BGSim
import BGSim.IR
import BGSim.Flat
import BGSim.Compile
import JSON3
import ModelingToolkit

# Unique names: test_flatten.jl already defines `_REPO`, `_fixture`, `_node`, ...
const _SIM_REPO = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _SIM_MODELS = joinpath(_SIM_REPO, "contracts", "fixtures", "model", "valid")
const _SIM_NEGATIVES = joinpath(@__DIR__, "fixtures", "negative")

_sim_fixture(name) = joinpath(_SIM_MODELS, name)
_sim_negative(name) = joinpath(_SIM_NEGATIVES, name)

function _sim_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params,
        "constants" => Dict{String,Any}(),
        "starts" => starts,
    )
end

_sim_ref(ref) = Dict{String,Any}("ref" => ref)
_sim_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _sim_conn(id, kind, from_node, from_port, to_node, to_port)
    return Dict{String,Any}(
        "id" => id,
        "kind" => kind,
        "from" => Dict{String,Any}("node" => from_node, "port" => from_port),
        "to" => Dict{String,Any}("node" => to_node, "port" => to_port),
    )
end

function _sim_model(name, nodes, connections;
    t_start = 0.0, t_end = 1.0, solver = "Rodas5P", reltol = 1.0e-9,
    abstol = 1.0e-11, points = 101)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...],
            "connections" => Any[connections...],
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => t_start,
            "t_end" => t_end,
            "solver" => solver,
            "reltol" => reltol,
            "abstol" => abstol,
            "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

_sim_flat(doc) = Compile.flatten(IR.parse_model(doc))
_sim_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

# ---------------------------------------------------------------------------------------
# Reading a run folder
# ---------------------------------------------------------------------------------------

function _sim_manifest(dir)
    return JSON3.read(read(joinpath(dir, "manifest.json"), String))
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _sim_columns(dir)
    m = _sim_manifest(dir)
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = read(joinpath(dir, "columns.f64"))
    @test length(raw) == 8 * n * (nsig + 1)
    columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
    out = Dict{String,Vector{Float64}}("time" => collect(columns[:, 1]))
    for (j, signal) in enumerate(m.signals)
        out[String(signal.id)] = collect(columns[:, j + 1])
    end
    return out
end

"""The stream file as a `(nsignals + 1) x n` matrix, so `rows[:, k]` is row `k`."""
function _sim_stream(dir)
    m = _sim_manifest(dir)
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = read(joinpath(dir, "stream.f64"))
    @test length(raw) == 8 * n * (nsig + 1)
    return reshape(reinterpret(Float64, raw), (nsig + 1, n))
end

# ---------------------------------------------------------------------------------------
# Inline models used by the lowering tests
# ---------------------------------------------------------------------------------------

const _FUN_BLOCK = """
@block Fun begin
    @inputs u::Real
    @outputs y::Real
    @outputs z::Real
    @equations begin
        y ~ abs(u) + clamp(u, -1.0, 1.0) + int(u, 2.0)
        z ~ min(u, 5.0) + max(u, 5.0) + sign(u) + round(u / 2.0) + hypot(u, 4.0) + atan(u, 4.0) + ifelse((u > 0) && (u != 1.0), 1.0, 0.0)
    end
end
"""

const _BOOM_BLOCK = """
@block Boom begin
    @outputs y::Real
    @variables x::Real = 1.0, [state = :prefer]
    @equations begin
        ddt(x) ~ x * x
        y ~ x
    end
end
"""

const _RAMP_BLOCK = """
@block Ramp begin
    @outputs y::Real
    @variables x::Real = 0.0, [state = :prefer]
    @equations begin
        ddt(x) ~ 1.0
        y ~ x
    end
end
"""

function _sim_fun_model()
    return _sim_model(
        "FunModel",
        [
            _sim_node("n1", "C1", _sim_ref("stdlib:sources/Constant");
                params = Dict("value" => "3.0")),
            _sim_node("n2", "F1", _sim_inline(_FUN_BLOCK)),
        ],
        [_sim_conn("c1", "signal", "n1", "y", "n2", "u")];
        solver = "Tsit5", reltol = 1.0e-9, abstol = 1.0e-11, points = 51,
    )
end

_sim_boom_model() = _sim_model(
    "Boom",
    [_sim_node("n1", "B1", _sim_inline(_BOOM_BLOCK))],
    Any[];
    t_end = 2.0, solver = "auto", points = 101,
)

_sim_ramp_model() = _sim_model(
    "Ramp",
    [_sim_node("n1", "R1", _sim_inline(_RAMP_BLOCK))],
    Any[];
    t_end = 10.0, solver = "Tsit5", points = 1001,
)

@testset "J1.5 lowering and simulation" begin
    @testset "RunSettings and the output grid" begin
        s = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0,
            output = Dict{String,Any}("mode" => "points", "points" => 11),
        )
        grid = BGSim.output_grid(s)
        @test length(grid) == 11
        @test grid[1] == 0.0
        @test grid[end] == 1.0
        @test all(isapprox.(diff(grid), 0.1; atol = 1e-12))

        interval = BGSim.RunSettings(
            t_start = 0.0, t_end = 0.25,
            output = Dict{String,Any}("mode" => "interval", "interval" => 0.1),
        )
        @test BGSim.output_grid(interval) == [0.0, 0.1, 0.2, 0.25]
        @test BGSim.to_namedtuple(s).solver == "auto"
        @test BGSim.to_namedtuple(s).output == (mode = "points", points = 11)

        @test_throws ArgumentError BGSim.RunSettings(t_start = 1.0, t_end = 0.0)
        @test_throws ArgumentError BGSim.RunSettings(reltol = 0.0)
        @test_throws ArgumentError BGSim.RunSettings(abstol = 0.0)
        @test_throws ArgumentError BGSim.RunSettings(max_step = -1.0)
        @test_throws ArgumentError BGSim.RunSettings(event_limit = -1)
        @test_throws ArgumentError BGSim.RunSettings(
            output = Dict{String,Any}("mode" => "points", "points" => 1)
        )
        @test_throws ArgumentError BGSim.RunSettings(
            output = Dict{String,Any}("mode" => "nope")
        )
        @test_throws ArgumentError BGSim.RunSettings(
            output = Dict{String,Any}("mode" => "interval", "interval" => 0.0)
        )

        # The fixture's settings parse to exactly the plan 3.3 values.
        raw = JSON3.read(read(_sim_fixture("model.dcmotor.json"), String)).settings
        fixture = BGSim.RunSettings(raw)
        @test fixture.t_start == 0.0
        @test fixture.t_end == 1.0
        @test fixture.solver == "auto"
        @test fixture.reltol == 1.0e-6
        @test fixture.abstol == 1.0e-8
        @test fixture.max_step === nothing
        @test fixture.output == (mode = "points", points = 5000)
        @test fixture.event_limit == 10000
    end

    @testset "expression lowering: functions, int and the nonsmooth seam" begin
        flat = _sim_flat(_sim_fun_model())
        @test isempty(_sim_errors(flat))
        @test flat.stats.states == 0          # no declared state; `int` adds one
        @test flat.stats.equations == 4
        # J2.3: every kink of the nonsmooth functions becomes a condition-only event. The
        # collector is a structural walk over the flat equations, in first-seen order and
        # without duplicates (the exact conditions are covered by `test_events.jl`).
        conditions = BGSim.nonsmooth_conditions(flat)
        @test conditions isa Vector{BGSim.Expr}
        @test !isempty(conditions)
        @test sprint(show, conditions) == sprint(show, BGSim.nonsmooth_conditions(flat))
        @test length(unique(sprint(show, c) for c in conditions)) == length(conditions)

        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0, solver = "Tsit5", reltol = 1.0e-9,
            abstol = 1.0e-11,
            output = Dict{String,Any}("mode" => "points", "points" => 51),
        )
        dir = mktempdir()
        result = simulate(flat; run_dir = dir, settings = settings)
        @test result.status == "done"
        @test isempty(_sim_errors(flat))
        @test result.stats.states == 1        # the hidden `int` state
        @test result.stats.equations == 5     # its D(state) equation

        columns = _sim_columns(dir)
        # y = abs(3) + clamp(3, -1, 1) + int(3, 2) = 3 + 1 + (2 + 3 t)
        @test isapprox(columns["F1/y"][1], 6.0; rtol = 1e-12)
        @test isapprox(columns["F1/y"][end], 9.0; rtol = 1e-8)
        # z: min 3, max 5, sign 1, round(1.5)=2, hypot(3,4)=5, atan(3,4), ifelse=1.
        @test isapprox(
            columns["F1/z"][1],
            3 + 5 + 1 + 2 + 5 + atan(3.0, 4.0) + 1.0;
            rtol = 1e-12,
        )
        @test maximum(abs.(columns["F1/z"] .- columns["F1/z"][1])) < 1e-12

        # The structural key ignores parameter values and start values, and follows a changed
        # equation (the cache/remake contract of decision D4).
        @test BGSim.compile_key(flat) ==
              BGSim.compile_key(BGSim.set_parameter_values(flat, Dict("C1/value" => 4.0)))
        @test BGSim.compile_key(flat) ==
              BGSim.compile_key(BGSim.set_start_values(flat, Dict("F1/y" => 1.0)))
        changed = _sim_fun_model()
        changed["diagram"]["nodes"][2]["block"]["inline"]["source"] = replace(
            _FUN_BLOCK, "round(u / 2.0)" => "round(u / 3.0)"
        )
        @test BGSim.compile_key(flat) != BGSim.compile_key(_sim_flat(changed))

        # Every solver the plan allows is wired to the right OrdinaryDiffEq sub-package.
        for solver in ("Rodas5P", "Tsit5", "FBDF", "Vern7")
            solver_settings = BGSim.RunSettings(
                t_start = 0.0, t_end = 0.25, solver = solver, reltol = 1.0e-8,
                abstol = 1.0e-10,
                output = Dict{String,Any}("mode" => "points", "points" => 26),
            )
            solver_result = simulate(flat; run_dir = mktempdir(), settings = solver_settings)
            @test solver_result.status == "done"
        end

        # An unsupported construct is a real E900 with the block path, never a silent zero.
        bad = _sim_fun_model()
        bad["diagram"]["nodes"][2]["block"]["inline"]["source"] = replace(
            _FUN_BLOCK, "int(u, 2.0)" => "int(u, u)"
        )
        bad_flat = _sim_flat(bad)
        @test isempty(_sim_errors(bad_flat))
        bad_dir = mktempdir()
        bad_result = simulate(bad_flat; run_dir = bad_dir, settings = settings)
        @test bad_result.status == "failed"
        lowering_error = only([x for x in bad_result.diagnostics if x.code == "E900"])
        @test occursin("start value of `int`", lowering_error.hint)
        @test lowering_error.path == "F1"
    end

    @testset "run files: stream.f64, columns.f64 and manifest.json" begin
        flat = Compile.flatten(IR.parse_model(_sim_fixture("model.rlc.iconic.json")))
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 0.5, solver = "Rodas5P", reltol = 1.0e-10,
            abstol = 1.0e-12,
            output = Dict{String,Any}("mode" => "points", "points" => 2001),
        )
        dir = mktempdir()
        seen_running = Ref(false)
        running_signals = Ref(0)
        seen_compile_phase = Ref(false)

        function progress(t, rows)
            if !seen_running[]
                manifest = _sim_manifest(dir)
                @test String(manifest.status) == "running"
                @test length(manifest.signals) == length(flat.signals)
                @test [String(manifest.signals[i].id) for i in eachindex(manifest.signals)] ==
                      [signal.id for signal in flat.signals]
                @test haskey(manifest, :stats)
                seen_running[] = true
                running_signals[] = length(manifest.signals)
            end
            return nothing
        end

        function phase_callback(name, t_s)
            if name == "mtkcompile" && !seen_compile_phase[]
                manifest = _sim_manifest(dir)
                @test String(manifest.status) == "running"
                @test length(manifest.signals) == length(flat.signals)
                seen_compile_phase[] = true
            end
            return nothing
        end

        result = simulate(
            flat; run_dir = dir, settings = settings, progress = progress,
            phase = phase_callback,
        )
        @test seen_running[]                       # REQ-1: the running manifest exists
        @test seen_compile_phase[]                 # ... already during mtkcompile
        @test running_signals[] == length(flat.signals)
        @test result.status == "done"
        @test isempty(result.diagnostics)

        manifest = _sim_manifest(dir)
        @test String(manifest.status) == "done"
        @test String(manifest.layout) == "columnar-f64-v1"
        @test String(manifest.model) == "RLCSeriesIconic"
        @test occursin(r"^[0-9a-f]{64}$", String(manifest.modelHash))
        @test Int(manifest.time.n) == 2001
        @test manifest.time.t0 == 0.0
        @test manifest.time.t1 == 0.5
        @test manifest.stats.states == flat.stats.states
        @test manifest.stats.equations == flat.stats.equations
        @test manifest.stats.steps > 0
        @test manifest.stats.sim_s > 0
        @test length(manifest.signals) == length(flat.signals)
        @test [String(s.id) for s in manifest.signals] == [s.id for s in flat.signals]
        @test all(s -> haskey(s, :path) && haskey(s, :type), manifest.signals)
        @test String(manifest.settings.solver) == "Rodas5P"

        # columns.f64 is the playback layout: the time column, then every signal column.
        raw = read(joinpath(dir, "columns.f64"))
        n = Int(manifest.time.n)
        nsig = length(manifest.signals)
        @test length(raw) == 8 * n * (nsig + 1)
        columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
        @test columns[:, 1] == collect(range(0.0, 0.5; length = n))
        @test raw[1:8] == zeros(UInt8, 8)          # t0 = 0.0 in little-endian Float64

        # stream.f64 is the same data row-major [t, v1 ... vn].
        rows = _sim_stream(dir)
        @test size(rows) == (nsig + 1, n)
        @test rows == permutedims(columns)

        # The convenience entry point flattens a model document itself (a path here).
        direct_dir = mktempdir()
        direct = simulate(
            _sim_fixture("model.rlc.bondgraph.json");
            run_dir = direct_dir, settings = settings,
        )
        @test direct.status == "done"
        @test isfile(joinpath(direct_dir, "columns.f64"))
        @test String(_sim_manifest(direct_dir).model) == "RLCSeriesBondGraph"

        # Known analytic value (plan 9.3): R = 10, L = 10 mH, C = 100 uF gives zeta = 0.5,
        # w0 = 1000 rad/s and a 16.3 % capacitor-voltage overshoot.
        data = _sim_columns(dir)
        peak = maximum(data["C1/p.e"])
        exact = 1 + exp(-pi * 0.5 / sqrt(1 - 0.25))
        @test isapprox(peak, exact; rtol = 2e-3)
        @test isapprox(data["C1/p.e"][end], 1.0; rtol = 1e-6)
    end

    @testset "recorder: duplicate event times and the running manifest" begin
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0,
            output = Dict{String,Any}("mode" => "points", "points" => 2),
        )
        signals = [(
            id = "A/x", unit = nothing, kind = "state", path = "A", type = "Real",
        )]
        dir = mktempdir()
        rec = BGSim.open_recorder(
            dir, "dup", "Dup", "0"^64, settings, signals, BGSim.Diagnostic[];
            capacity = 4, states = 1, equations = 1,
        )
        # J2.3 records the two sides of an event at the same time.
        BGSim.record_row!(rec, 0.5, [1.0])
        BGSim.record_row!(rec, 0.5, [2.0])
        BGSim.record_row!(rec, 1.0, [3.0])
        manifest = BGSim.finish_recorder!(
            rec, "done", BGSim._zero_stats(1, 1), BGSim.Diagnostic[]
        )
        @test Int(manifest.time.n) == 3
        @test manifest.time.t0 == 0.5
        @test manifest.time.t1 == 1.0

        raw = read(joinpath(dir, "columns.f64"))
        @test length(raw) == 8 * 3 * 2
        columns = reshape(reinterpret(Float64, raw), (3, 2))
        @test columns[:, 1] == [0.5, 0.5, 1.0]
        @test columns[:, 2] == [1.0, 2.0, 3.0]

        stream_raw = read(joinpath(dir, "stream.f64"))
        @test length(stream_raw) == 8 * 3 * 2
        rows = reshape(reinterpret(Float64, stream_raw), (2, 3))
        @test rows[:, 1] == [0.5, 1.0]
        @test rows[:, 2] == [0.5, 2.0]
        @test rows[:, 3] == [1.0, 3.0]
        @test rows == permutedims(columns)
    end

    @testset "DC motor: steady state and iconic vs bond graph" begin
        R, k, d = 2.0, 0.05, 1.0e-6
        target = k * 12.0 / (R * d + k^2)
        @test isapprox(target, 239.80815347721824; rtol = 1e-12)

        iconic = Compile.flatten(IR.parse_model(_sim_fixture("model.dcmotor.json")))
        bond = Compile.flatten(
            IR.parse_model(_sim_fixture("model.dcmotor.bondgraph.json"))
        )
        @test isempty(_sim_errors(iconic))
        @test isempty(_sim_errors(bond))
        @test iconic.stats.states == 2 && iconic.stats.equations == 26
        @test bond.stats.states == 2 && bond.stats.equations == 16
        @test length([x for x in bond.diagnostics if x.code == "W205"]) == 2

        # Lowering keeps exactly the two differential states; the port power e*f is an
        # observed variable in the same signal-id dictionary as the unknowns.
        BGSim.clear_compile_cache!()
        lowered = BGSim.lower_model(iconic; t_start = 0.0, t_end = 1.0)
        @test !lowered.cache_hit
        @test length(ModelingToolkit.unknowns(lowered.model.system)) == 2
        @test haskey(lowered.model.vars, "Motor1/shaft.P")
        @test haskey(lowered.model.vars, "Motor1/shaft.f")

        # The fixture settings (auto -> Tsit5 at 1e-6) are enough for the 1e-4 check.
        iconic_settings = BGSim.RunSettings(
            JSON3.read(read(_sim_fixture("model.dcmotor.json"), String)).settings
        )
        bond_settings = BGSim.RunSettings(
            JSON3.read(read(_sim_fixture("model.dcmotor.bondgraph.json"), String)).settings
        )
        iconic_dir = mktempdir()
        bond_dir = mktempdir()
        iconic_run = simulate(iconic; run_dir = iconic_dir, settings = iconic_settings)
        bond_run = simulate(bond; run_dir = bond_dir, settings = bond_settings)
        @test iconic_run.status == "done"
        @test bond_run.status == "done"
        @test any(x -> x.code == "W205", bond_run.diagnostics)

        iconic_columns = _sim_columns(iconic_dir)
        bond_columns = _sim_columns(bond_dir)
        @test isapprox(iconic_columns["Motor1/shaft.f"][end], target; rtol = 1e-4)
        @test isapprox(bond_columns["IJ/p.f"][end], target; rtol = 1e-4)
        # The motor current at steady state: T = k*i = d*omega.
        @test isapprox(iconic_columns["Motor1/i"][end], d * target / k; rtol = 1e-4)

        # Agreement: with a tolerance that makes 1e-6 meaningful, compare the settled part
        # (the bond graph starts from a constant 12 V while the iconic model has its step at
        # t = 0.01 s, so the transient up to 0.5 s is not comparable by construction).
        tight = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0, solver = "Rodas5P", reltol = 1.0e-10,
            abstol = 1.0e-12,
            output = Dict{String,Any}("mode" => "points", "points" => 1001),
        )
        iconic_tight = mktempdir()
        bond_tight = mktempdir()
        rt_i = simulate(iconic; run_dir = iconic_tight, settings = tight)
        rt_b = simulate(bond; run_dir = bond_tight, settings = tight)
        @test rt_i.status == "done" && rt_b.status == "done"
        ci = _sim_columns(iconic_tight)
        cb = _sim_columns(bond_tight)
        # J2.3 records a condition-only row pair at the Step kink, so the two runs need not
        # have the same number of rows even though they share the whole output grid. Compare
        # on the times both files contain (the duplicate event rows collapse to one time).
        common = sort!(collect(intersect(Set(ci["time"]), Set(cb["time"]))))
        ci_at = [findfirst(==(t), ci["time"]) for t in common]
        cb_at = [findfirst(==(t), cb["time"]) for t in common]
        settled = common .>= 0.5
        speed_diff = maximum(abs.(
            ci["Motor1/shaft.f"][ci_at][settled] .- cb["IJ/p.f"][cb_at][settled]
        ))
        current_diff = maximum(abs.(
            ci["Motor1/i"][ci_at][settled] .- cb["IL/p.f"][cb_at][settled]
        ))
        @test speed_diff < 1.0e-6
        @test current_diff < 1.0e-8
        # The whole settled trajectory, not only the final value, is in steady state.
        @test maximum(abs.(ci["Motor1/shaft.f"][ci_at][settled] .- target)) < 1.0e-6
        @test maximum(abs.(cb["IJ/p.f"][cb_at][settled] .- target)) < 1.0e-6
        println(
            "J1.5 DC motor: omega(1 s) = ", ci["Motor1/shaft.f"][end],
            " rad/s (target ", target, "), iconic-vs-bondgraph max |domega| = ",
            speed_diff, " rad/s, max |di| = ", current_diff, " A",
        )
    end

    @testset "derivative-causal inertias still simulate" begin
        # Se -> 1-junction -> two I elements. Both inertias share the junction
        # velocity, so SCAP puts one in derivative causality (W201). The run must
        # still record every row and solve the dependent momentum algebraically;
        # this is the regression for the reported "adding an I yields no data".
        nodes = [
            _sim_node("n1", "Se1", _sim_ref("stdlib:bondgraph/Se");
                params = Dict("e" => "2.0")),
            _sim_node("n2", "J1", Dict("junction" => "1")),
            _sim_node("n3", "I1", _sim_ref("stdlib:bondgraph/I");
                params = Dict("i" => "2.0")),
            _sim_node("n4", "I2", _sim_ref("stdlib:bondgraph/I");
                params = Dict("i" => "2.0")),
        ]
        connections = [
            _sim_conn("c1", "bond", "n1", "p", "n2", nothing),
            _sim_conn("c2", "bond", "n2", nothing, "n3", "p"),
            _sim_conn("c3", "bond", "n2", nothing, "n4", "p"),
        ]
        flat = _sim_flat(_sim_model("DerivativeI", nodes, connections;
            t_end = 1.0, points = 11))
        @test isempty(_sim_errors(flat))
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0,
            output = Dict{String,Any}("mode" => "points", "points" => 11),
        )
        dir = mktempdir()
        result = simulate(flat; run_dir = dir, run_id = "derivative-i", settings = settings)
        @test result.status == "done"
        @test any(d -> d.code == "W201", result.diagnostics)
        @test !any(d -> d.code in ("E900", "E901"), result.diagnostics)
        data = _sim_columns(dir)
        @test length(data["time"]) == 11
        @test all(isfinite, data["I1/P"])
        @test all(isfinite, data["I2/P"])
        @test isapprox(data["I1/p.f"][end], 0.5; rtol = 1.0e-6)
        @test isapprox(data["I2/p.f"][end], 0.5; rtol = 1.0e-6)
        @test isapprox(data["I1/P"][end], 1.0; rtol = 1.0e-6)
        @test isapprox(data["I2/P"][end], 1.0; rtol = 1.0e-6)
    end

    @testset "algebraic starts are guesses, not equations (FIX-M2-1)" begin
        # Se -> 1-junction -> TF(n=2) -> R(3). At t = 0 the transformer's second-port
        # effort is 0.5 and the resistor flow is 1/6, both algebraic and non-zero. Passing
        # a start for them made MTK add an overdetermined initialisation equation; they are
        # now guesses, so the values are solved from the equations.
        fixture = joinpath(@__DIR__, "fixtures", "causality", "tf_chain.json")
        flat = Compile.flatten(IR.parse_model(read(fixture, String)))
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 0.001, solver = "Rodas5P",
            reltol = 1.0e-10, abstol = 1.0e-12,
            output = Dict{String,Any}("mode" => "points", "points" => 3),
        )
        dir = mktempdir()
        result = simulate(flat; run_dir = dir, run_id = "tf-chain", settings = settings)
        @test result.status == "done"
        @test !any(d -> d.code in ("E103", "E900", "E901"), result.diagnostics)
        data = _sim_columns(dir)
        @test all(data["TF1/p2.e"] .== 0.5)
        @test all(isapprox.(data["R1/p.f"], 1 / 6; atol = 1.0e-12))
        @test all(isapprox.(data["TF1/p1.f"], 1 / 12; atol = 1.0e-12))
    end

    @testset "RLC: analytic overshoot and iconic vs bond graph" begin
        iconic = Compile.flatten(IR.parse_model(_sim_fixture("model.rlc.iconic.json")))
        bond = Compile.flatten(
            IR.parse_model(_sim_fixture("model.rlc.bondgraph.json"))
        )
        @test isempty(_sim_errors(iconic))
        @test isempty(_sim_errors(bond))
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 0.5, solver = "Rodas5P", reltol = 1.0e-10,
            abstol = 1.0e-12,
            output = Dict{String,Any}("mode" => "points", "points" => 2001),
        )
        iconic_dir = mktempdir()
        bond_dir = mktempdir()
        @test simulate(iconic; run_dir = iconic_dir, settings = settings).status == "done"
        @test simulate(bond; run_dir = bond_dir, settings = settings).status == "done"
        ci = _sim_columns(iconic_dir)
        cb = _sim_columns(bond_dir)
        # The iconic half has a Step kink (recorded as a condition-only event pair); align
        # the two runs by time before comparing their trajectories.
        common = sort!(collect(intersect(Set(ci["time"]), Set(cb["time"]))))
        ci_at = [findfirst(==(t), ci["time"]) for t in common]
        cb_at = [findfirst(==(t), cb["time"]) for t in common]
        difference = maximum(abs.(
            ci["C1/p.e"][ci_at] .- cb["C1/p.e"][cb_at]
        ))
        @test difference < 1.0e-6
        zeta = 0.5
        exact = 1 + exp(-pi * zeta / sqrt(1 - zeta^2))
        @test isapprox(maximum(ci["C1/p.e"]), exact; rtol = 2e-3)
        @test isapprox(maximum(cb["C1/p.e"]), exact; rtol = 2e-3)
        println(
            "J1.5 RLC: peak = ", maximum(ci["C1/p.e"]), " V (analytic ", exact,
            " V), iconic-vs-bondgraph max |du_C| = ", difference, " V",
        )
    end

    @testset "cancellation, E901 and a refused model" begin
        # A blow-up: D(x) = x^2 from x = 1 ends at t = 1 with retcode Unstable.
        boom = _sim_flat(_sim_boom_model())
        @test isempty(_sim_errors(boom))
        boom_dir = mktempdir()
        boom_settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 2.0, solver = "auto",
            output = Dict{String,Any}("mode" => "points", "points" => 101),
        )
        boom_result = simulate(boom; run_dir = boom_dir, settings = boom_settings)
        @test boom_result.status == "failed"
        @test !isempty(boom_result.diagnostics)
        solver_error = only([x for x in boom_result.diagnostics if x.code == "E901"])
        @test occursin("t = ", solver_error.message)
        @test occursin("Unstable", solver_error.message)
        @test solver_error.hint !== nothing
        @test occursin("B1/x", solver_error.hint)
        @test solver_error.path == "B1"
        manifest = _sim_manifest(boom_dir)
        @test String(manifest.status) == "failed"
        @test any(String(x.code) == "E901" for x in manifest.diagnostics)
        @test manifest.stats.steps > 0

        # Cancellation: the first progress call sets the atomic flag.
        ramp = _sim_flat(_sim_ramp_model())
        cancel_flag = Threads.Atomic{Bool}(false)
        calls = Ref(0)
        function progress(t, rows)
            calls[] += 1
            cancel_flag[] = true
            return nothing
        end
        cancel_dir = mktempdir()
        cancel_result = simulate(
            ramp; run_dir = cancel_dir, cancel = cancel_flag, progress = progress,
        )
        @test cancel_result.status == "cancelled"
        @test calls[] >= 1
        manifest = _sim_manifest(cancel_dir)
        @test String(manifest.status) == "cancelled"
        @test Int(manifest.time.n) == cancel_result.time.n
        @test filesize(joinpath(cancel_dir, "columns.f64")) ==
              8 * Int(manifest.time.n) * (length(manifest.signals) + 1)
        @test filesize(joinpath(cancel_dir, "stream.f64")) ==
              8 * Int(manifest.time.n) * (length(manifest.signals) + 1)

        # A flat model that already has an error diagnostic is refused; only the manifest
        # is written, with status failed.
        broken = Compile.flatten(IR.parse_model(_sim_negative("e103_unbalanced.json")))
        @test !isempty(_sim_errors(broken))
        broken_dir = mktempdir()
        broken_result = simulate(broken; run_dir = broken_dir)
        @test broken_result.status == "failed"
        @test any(x -> x.severity == "error", broken_result.diagnostics)
        @test readdir(broken_dir) == ["manifest.json"]
        @test String(_sim_manifest(broken_dir).status) == "failed"
    end

    @testset "parameter-only re-run hits the cache and meets the 5.12 targets" begin
        flat = Compile.flatten(IR.parse_model(_sim_fixture("model.dcmotor.json")))
        @test isempty(_sim_errors(flat))
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0, solver = "auto", reltol = 1.0e-6,
            abstol = 1.0e-8,
            output = Dict{String,Any}("mode" => "points", "points" => 101),
        )

        BGSim.clear_compile_cache!()
        first_dir = mktempdir()
        started = time_ns()
        first_run = simulate(flat; run_dir = first_dir, settings = settings)
        first_run_s = (time_ns() - started) / 1.0e9
        @test first_run.status == "done"
        @test !first_run.cache_hit
        @test first_run_s < 10.0

        # A parameter-only change keeps the structural key and hits the cache.
        flat2 = BGSim.set_parameter_values(flat, Dict("Damp1/d" => 2.0e-6))
        @test BGSim.compile_key(flat2) == BGSim.compile_key(flat)
        warm_dir = mktempdir()
        warm = simulate(flat2; run_dir = warm_dir, settings = settings)
        @test warm.cache_hit
        @test warm.status == "done"

        # NOTES.md: the first re-run after a parameter change pays JIT. Measure the second.
        timed_dir = mktempdir()
        timed = simulate(flat2; run_dir = timed_dir, settings = settings)
        @test timed.cache_hit
        @test timed.status == "done"
        @test timed.first_data_s < 0.3
        target = 0.05 * 12.0 / (2.0 * 2.0e-6 + 0.05^2)
        columns = _sim_columns(timed_dir)
        @test isapprox(columns["Motor1/shaft.f"][end], target; rtol = 1e-4)

        # Start-only changes also keep the key and really move the initial state.
        flat3 = BGSim.set_start_values(flat, Dict("Motor1/w_rel" => 100.0))
        @test BGSim.compile_key(flat3) == BGSim.compile_key(flat)
        start_dir = mktempdir()
        started_run = simulate(flat3; run_dir = start_dir, settings = settings)
        @test started_run.cache_hit
        @test isapprox(_sim_columns(start_dir)["Motor1/shaft.f"][1], 100.0; rtol = 1e-12)

        println(
            "J1.5 timings: first run (compile+cache miss) = ",
            round(1000 * first_run_s; digits = 1),
            " ms (target < 10000 ms), parameter-only first data after one warm-up = ",
            round(1000 * timed.first_data_s; digits = 1), " ms (target < 300 ms)",
        )
    end
end
