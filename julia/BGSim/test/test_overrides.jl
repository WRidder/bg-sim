# Dashboard inputs (plan/DASHBOARD_PLAN.md): run-wide parameter overrides and the timed
# parameter schedule, checked against the analytic first-order step response
#
#     U (Constant, value u) -> G (FirstOrder, gain k, time constant tau)
#     x' = (u - x) / tau,  x(0) = 0,  y = k x
#
#   * an override replaces a parameter for the whole run, without touching the document;
#   * an override is applied before flattening, so a start value derived from it follows;
#   * a schedule step at t = 1 changes u and k exactly there: two rows at t = 1 (left and right
#     limit), and the analytic solution after it;
#   * a step at t_start acts as an override; steps after t_end never apply;
#   * bad targets are refused with a message; a replay reapplies the stored inputs.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

function _ov_doc(; k = "1.0", tau = "0.5", u = "1.0", t_end = 2.0)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => "FirstOrderInputs",
        "diagram" => Dict{String,Any}(
            "nodes" => Any[
                Dict{String,Any}(
                    "id" => "n1", "name" => "U", "block" => Dict("ref" => "stdlib:sources/Constant"),
                    "position" => Dict("x" => 0, "y" => 0), "params" => Dict("value" => u),
                ),
                Dict{String,Any}(
                    "id" => "n2", "name" => "G",
                    "block" => Dict("ref" => "stdlib:continuous/FirstOrder"),
                    "position" => Dict("x" => 200, "y" => 0),
                    "params" => Dict("k" => k, "tau" => tau),
                ),
                Dict{String,Any}(
                    "id" => "n3", "name" => "S",
                    "block" => Dict("subsystem" => Dict(
                        "ports" => Any[],
                        "diagram" => Dict(
                            "nodes" => Any[Dict{String,Any}(
                                "id" => "s1", "name" => "I",
                                "block" => Dict("ref" => "stdlib:continuous/Integrator"),
                                "position" => Dict("x" => 0, "y" => 0),
                                "params" => Dict("upper" => "1e30"),
                            ), Dict{String,Any}(
                                "id" => "s2", "name" => "C",
                                "block" => Dict("ref" => "stdlib:sources/Constant"),
                                "position" => Dict("x" => 0, "y" => 0),
                                "params" => Dict("value" => "0.25"),
                            )],
                            "connections" => Any[Dict{String,Any}(
                                "id" => "sc1", "kind" => "signal",
                                "from" => Dict("node" => "s2", "port" => "y"),
                                "to" => Dict("node" => "s1", "port" => "u"),
                            )],
                        ),
                    )),
                    "position" => Dict("x" => 0, "y" => 200),
                ),
            ],
            "connections" => Any[Dict{String,Any}(
                "id" => "c1", "kind" => "signal",
                "from" => Dict("node" => "n1", "port" => "y"),
                "to" => Dict("node" => "n2", "port" => "u"),
            )],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "auto", "reltol" => 1e-9,
            "abstol" => 1e-11, "max_step" => nothing,
            "output" => Dict("mode" => "points", "points" => 201), "event_limit" => 1000,
        ),
        "dashboard" => Dict{String,Any}("cards" => Any[Dict{String,Any}(
            "id" => "c1", "kind" => "slider", "size" => "2x1", "parameter" => "G/k", "value" => 5,
        )]),
    )
end

function _ov_columns(dir)
    m = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(m.time.n)
    raw = read(joinpath(dir, "columns.f64"))
    cols = reshape(reinterpret(Float64, raw), (n, length(m.signals) + 1))
    out = Dict{String,Vector{Float64}}("time" => collect(cols[:, 1]))
    for (j, s) in enumerate(m.signals)
        out[String(s.id)] = collect(cols[:, j + 1])
    end
    return m, out
end

# Run the document with run.start-shaped inputs, the way the worker does.
function _ov_run(doc; overrides = nothing, schedule = nothing)
    inputs = parse_parameter_inputs(overrides, schedule)
    md = IR.parse_model(doc)
    settings = BGSim.RunSettings(md.settings)
    start, steps = BGSim.start_inputs(inputs, settings.t_start, settings.t_end)
    flat = flatten_with_overrides(md, start)
    BGSim.check_schedule_targets(flat, steps)
    dir = mktempdir()
    BGSim.write_run_model(dir, doc, nothing; inputs = isempty(inputs) ? nothing : inputs)
    result = simulate(
        flat; run_dir = dir, run_id = "ov", settings = settings, parameter_schedule = steps,
        manifest_extra = isempty(inputs) ? nothing : BGSim.parameter_inputs_manifest(inputs),
    )
    @test result.status == "done"
    return dir
end

_ov_rows(cols, t) = findall(s -> abs(s - t) < 1e-9, cols["time"])
_ov_at(cols, id, t) = cols[id][last(_ov_rows(cols, t))]

@testset "dashboard inputs: parameter overrides and schedule" begin
    tau = 0.5
    x(t) = 1 - exp(-t / tau)

    @testset "the dashboard does not change the model" begin
        _, cols = _ov_columns(_ov_run(_ov_doc()))
        @test _ov_at(cols, "G/y", 2.0) ≈ x(2.0) rtol = 1e-6
    end

    @testset "an override replaces the parameter for the whole run" begin
        dir = _ov_run(_ov_doc(); overrides = [Dict("target" => "G/k", "value" => 2.0)])
        m, cols = _ov_columns(dir)
        for t in (0.5, 1.0, 2.0)
            @test _ov_at(cols, "G/y", t) ≈ 2 * x(t) rtol = 1e-6
        end
        @test m.parameterOverrides[1].target == "G/k"
        @test m.parameterOverrides[1].value == 2.0
        @test !haskey(m, :parameterSchedule)
    end

    @testset "an override inside a subsystem and an integer value" begin
        dir = _ov_run(_ov_doc(); overrides = [
            Dict("target" => "S/C/value", "value" => 2), Dict("target" => "G/tau", "value" => 0.25),
        ])
        _, cols = _ov_columns(dir)
        @test _ov_at(cols, "S/I/y", 2.0) ≈ 4.0 rtol = 1e-6
        @test _ov_at(cols, "G/y", 1.0) ≈ 1 - exp(-1.0 / 0.25) rtol = 1e-6
    end

    @testset "a schedule step at t = 1 changes u and k exactly there" begin
        schedule = [
            Dict("t" => 1.0, "target" => "U/value", "value" => 2.0),
            Dict("t" => 1.0, "target" => "G/k", "value" => 3.0),
        ]
        dir = _ov_run(_ov_doc(); schedule = schedule)
        m, cols = _ov_columns(dir)
        rows = _ov_rows(cols, 1.0)
        @test length(rows) == 2  # the left and the right limit
        x1 = x(1.0)
        @test cols["G/y"][rows[1]] ≈ x1 rtol = 1e-6
        @test cols["G/y"][rows[2]] ≈ 3 * x1 rtol = 1e-6
        @test cols["U/y"][rows[1]] ≈ 1.0
        @test cols["U/y"][rows[2]] ≈ 2.0
        xs(t) = 2 - (2 - x1) * exp(-(t - 1) / tau)
        for t in (1.5, 2.0)
            @test _ov_at(cols, "G/y", t) ≈ 3 * xs(t) rtol = 1e-6
        end
        @test _ov_at(cols, "G/y", 0.5) ≈ x(0.5) rtol = 1e-6
        @test length(m.parameterSchedule) == 2
        @test m.parameterSchedule[1].t == 1.0

        # A replay of the stored run reapplies the schedule bit for bit.
        replay = mktempdir()
        BGSim.replay_run(dir; run_dir = replay, run_id = "ov-replay")
        @test read(joinpath(replay, "columns.f64")) == read(joinpath(dir, "columns.f64"))
        rm_, _ = _ov_columns(replay)
        @test length(rm_.parameterSchedule) == 2
    end

    @testset "a step between grid points is its own target" begin
        dir = _ov_run(_ov_doc(); schedule = [Dict("t" => 1.0049, "target" => "U/value", "value" => 0.0)])
        _, cols = _ov_columns(dir)
        rows = _ov_rows(cols, 1.0049)
        @test length(rows) == 2
        x1 = x(1.0049)
        @test _ov_at(cols, "G/y", 2.0) ≈ x1 * exp(-(2.0 - 1.0049) / tau) rtol = 1e-6
    end

    @testset "a step at t_start is an override, a step after t_end never applies" begin
        dir = _ov_run(_ov_doc(); schedule = [
            Dict("t" => 0.0, "target" => "G/k", "value" => 4.0),
            Dict("t" => 5.0, "target" => "G/k", "value" => 9.0),
        ])
        _, cols = _ov_columns(dir)
        @test _ov_at(cols, "G/y", 2.0) ≈ 4 * x(2.0) rtol = 1e-6
        @test length(_ov_rows(cols, 2.0)) == 1
    end

    @testset "bad inputs are refused with a message" begin
        md = IR.parse_model(_ov_doc())
        err = try
            flatten_with_overrides(md, ["G/kk" => 1.0]); nothing
        catch e
            e
        end
        # `kk` is not declared by FirstOrder: flattening reports it (or the check names it).
        @test err isa ArgumentError ||
              any(d -> d.severity == "error", flatten_with_overrides(IR.parse_model(_ov_doc()), ["G/kk" => 1.0]).diagnostics)
        @test_throws ArgumentError flatten_with_overrides(IR.parse_model(_ov_doc()), ["Nope/k" => 1.0])
        flat = Compile.flatten(IR.parse_model(_ov_doc()))
        @test_throws ArgumentError BGSim.check_schedule_targets(
            flat, [BGSim.ParameterStepSpec(1.0, "G/zz", 1.0)],
        )
        @test_throws ArgumentError parse_parameter_inputs([Dict("target" => "G/k")], nothing)
        @test_throws ArgumentError parse_parameter_inputs(
            [Dict("target" => "G/k", "value" => 1.0, "kind" => "global")], nothing,
        )
        @test_throws ArgumentError parse_parameter_inputs(
            nothing, [Dict("t" => NaN, "target" => "G/k", "value" => 1.0)],
        )
        @test_throws ArgumentError parse_parameter_inputs(
            nothing, [Dict("t" => 1.0, "target" => "k", "value" => 1.0)],
        )
    end

    # model.global-parameters.json: m = 2, rate = 4*m, x0 = sqrt(m) + 0.5; the integrator
    # starts at x0 and integrates Source/Rate = rate, so y(t) = x0 + rate t on [0, 1].
    @testset "a global override is applied before static evaluation (kind global)" begin
        fixture = joinpath(@__DIR__, "..", "..", "..", "contracts", "fixtures", "model",
            "valid", "model.global-parameters.json")
        doc = JSON3.read(read(fixture, String), Dict{String,Any})
        y(m, rate, t) = sqrt(m) + 0.5 + rate * t

        dir = _ov_run(doc; overrides = [Dict("target" => "global:m", "kind" => "global",
            "value" => 3)])
        manifest, cols = _ov_columns(dir)
        @test cols["Int1/y"][1] ≈ y(3, 12, 0.0) atol = 1e-9
        @test cols["Int1/y"][end] ≈ y(3, 12, 1.0) atol = 1e-6
        @test manifest.parameterOverrides[1].kind == "global"
        @test manifest.parameterOverrides[1].target == "global:m"

        # The kind may be left out (the prefix says it); a block override on top wins over
        # the global-derived expression of that block.
        dir2 = _ov_run(doc; overrides = [
            Dict("target" => "global:m", "value" => 3),
            Dict("target" => "Source/Rate/value", "value" => 1),
        ])
        _, cols2 = _ov_columns(dir2)
        @test cols2["Int1/y"][1] ≈ y(3, 0, 0.0) atol = 1e-9
        @test cols2["Int1/y"][end] ≈ y(3, 1, 1.0) atol = 1e-6

        # A replay reapplies the stored global override.
        replay = BGSim.load_run_flat(dir)
        @test any(p -> p.id == "Source/Rate/value" && p.value == 12, replay.parameters)

        md = IR.parse_model(doc)
        @test_throws ArgumentError flatten_with_overrides(md, ["global:nope" => 1.0])
        @test_throws ArgumentError parse_parameter_inputs(
            [Dict("target" => "global:m", "kind" => "block", "value" => 1)], nothing,
        )
        @test_throws ArgumentError parse_parameter_inputs(
            [Dict("target" => "m", "kind" => "global", "value" => 1)], nothing,
        )
        @test_throws ArgumentError parse_parameter_inputs(
            [Dict("target" => "global:m", "value" => true)], nothing,
        )
        # Globals are folded at compile time: they cannot be scheduled.
        @test_throws ArgumentError parse_parameter_inputs(
            nothing, [Dict("t" => 0.5, "target" => "global:m", "value" => 1)],
        )
    end
end
