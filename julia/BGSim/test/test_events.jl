# Work package J2.3: @events, nonsmooth switching conditions, event recording and W206.
#
# Every model below goes through the real language pipeline
# (parse -> flatten -> lower -> simulate); no MTK equations are written by hand.
#
#   * the plan 9.2 bouncing ball: first impact 0.45152 s (abs 1e-6), second 1.17396 s
#     (abs 1e-5), peak after the first bounce 0.64 m (rtol 1e-4), with the event recorded
#     twice at the same t (left and right limits);
#   * a relay with hysteresis whose three switching times are 1/12, 7/12 and 13/12 s
#     (abs 1e-8), including the recorded left/right state values;
#   * the Zenonian limit of the bouncing ball (t_end beyond 4.06 s with event_limit = 25):
#     W206 in the manifest, status done, no E901 and no crash;
#   * condition-only callbacks from the nonsmooth functions land on the kinks.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

const _EV_BALL = """
@block Ball begin
    @parameters begin
        g::Real = 9.81, [unit = "m/s^2"]
        e::Real = 0.8, [min = 0, max = 1, description = "restitution"]
    end
    @variables begin
        h::Real = 1.0, [unit = "m"]
        v::Real = 0.0, [unit = "m/s"]
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

# The relay state `y` is a genuine differential state so `mtkcompile` keeps it; the tiny
# decay is far below every tolerance used here and only exists to keep the state from being
# eliminated as a trivial constant (a zero derivative is folded away by MTK).
const _EV_RELAY = """
@block Relay begin
    @parameters begin
        w::Real = 6.283185307179586, [unit = "rad/s"]
        hi::Real = 0.5
        lo::Real = -0.5
    end
    @variables begin
        x::Real = 0.0
        z::Real = 1.0
        y::Real = 0.0
    end
    @outputs stateout::Real
    @equations begin
        ddt(x) ~ w * z
        ddt(z) ~ -w * x
        ddt(y) ~ -1.0e-6 * y
        stateout ~ y
    end
    @events begin
        x > hi => begin
            reinit(y, 1.0)
        end
        x < lo => begin
            reinit(y, 0.0)
        end
    end
end
"""

const _EV_SMOOTH = """
@block Smooth begin
    @variables x::Real = -2.0
    @outputs y::Real
    @equations begin
        ddt(x) ~ 1.0
        y ~ abs(x) + clamp(x, -1.0, 1.0) + min(x, 2.0) + max(x, -2.0) + sign(x)
    end
end
"""

function _ev_node(id, name, source)
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => source)),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(),
        "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
end

function _ev_model(name, source; t_end = 1.0, event_limit = 10000, points = 1001,
    solver = "Rodas5P", reltol = 1.0e-10, abstol = 1.0e-10)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[_ev_node("n1", "Plant", source)],
            "connections" => Any[],
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0,
            "t_end" => t_end,
            "solver" => solver,
            "reltol" => reltol,
            "abstol" => abstol,
            "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => event_limit,
        ),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

_ev_flat(doc) = Compile.flatten(IR.parse_model(doc))
_ev_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _ev_manifest(dir)
    return JSON3.read(read(joinpath(dir, "manifest.json"), String))
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _ev_columns(dir)
    m = _ev_manifest(dir)
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

"""Every group of equal consecutive `t` values: one event instant recorded as left/right."""
function _ev_event_groups(times)
    groups = Float64[]
    i = 1
    while i <= length(times)
        j = i
        while j < length(times) && times[j + 1] == times[i]
            j += 1
        end
        j > i && push!(groups, times[i])
        i = j + 1
    end
    return groups
end

function _ev_run(doc; t_end = nothing)
    if t_end !== nothing
        doc["settings"]["t_end"] = t_end
    end
    flat = _ev_flat(doc)
    @test isempty(_ev_errors(flat))
    dir = mktempdir()
    result = simulate(
        flat; run_dir = dir, settings = BGSim.RunSettings(doc["settings"])
    )
    return result, dir, _ev_columns(dir)
end

@testset "J2.3 events and nonsmooth" begin
    @testset "bouncing ball (plan 9.2)" begin
        g = 9.81
        e = 0.8
        h0 = 1.0
        t1 = sqrt(2 * h0 / g)
        v_impact = sqrt(2 * g * h0)
        t2 = t1 + 2 * e * v_impact / g
        doc = _ev_model("EvBall", _EV_BALL; t_end = 3.5, points = 1001)
        flat = _ev_flat(doc)
        @test isempty(_ev_errors(flat))
        # The condition is normalised to `-h` (a < b becomes b - a) and the body to one
        # affect equation; the AST never contains MTK objects.
        @test length(flat.events) == 1
        @test isempty(BGSim.nonsmooth_conditions(flat))

        result, dir, columns = _ev_run(doc)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])

        times = columns["time"]
        groups = _ev_event_groups(times)
        @test length(groups) >= 3
        @test abs(groups[1] - t1) <= 1.0e-6
        @test abs(groups[2] - t2) <= 1.0e-5
        @test result.stats.events == length(groups)

        # The event instant is written twice at exactly the same t: pre-affect (left) and
        # post-affect (right) velocity, with the height on the ground in both rows.
        first_left = findfirst(==(groups[1]), times)
        first_right = findlast(==(groups[1]), times)
        @test first_left !== nothing && first_right == first_left + 1
        @test times[first_left] == times[first_right]
        @test columns["Plant/h"][first_left] <= 1.0e-9
        @test columns["Plant/h"][first_right] <= 1.0e-9
        @test columns["Plant/v"][first_left] < 0
        @test columns["Plant/v"][first_right] > 0
        @test isapprox(columns["Plant/v"][first_right], e * v_impact; rtol = 1.0e-4)

        # Peak after the first bounce: e^2 * h0 = 0.64 m. Restrict to the interval between
        # the first and the second impact so the release height cannot win.
        after_first = (times .> groups[1]) .& (times .< groups[2])
        peak = maximum(columns["Plant/h"][after_first])
        @test isapprox(peak, e^2 * h0; rtol = 1.0e-4)
        @test isapprox(peak, 0.64; rtol = 1.0e-4)

        manifest = _ev_manifest(dir)
        @test Int(manifest.stats.events) == length(groups)
    end

    @testset "relay with hysteresis" begin
        doc = _ev_model("EvRelay", _EV_RELAY; t_end = 1.2, points = 121)
        flat = _ev_flat(doc)
        @test isempty(_ev_errors(flat))
        @test length(flat.events) == 2

        result, _, columns = _ev_run(doc)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])

        times = columns["time"]
        all_groups = _ev_event_groups(times)
        # A one-directional callback still detects the falling zero crossing (the solver
        # saves it) but does not fire: the relay state changes only on the rising edges.
        state = columns["Plant/stateout"]
        switching = Float64[]
        direction = Int[]
        for t in all_groups
            left = findfirst(==(t), times)
            right = findlast(==(t), times)
            if state[right] != state[left]
                push!(switching, t)
                push!(direction, state[right] > state[left] ? 1 : -1)
            end
        end
        @test length(switching) == 3
        @test direction == [1, -1, 1]
        analytic = [1 / 12, 7 / 12, 13 / 12]
        @test all(abs.(switching .- analytic) .<= 1.0e-8)
        @test result.stats.events == 3

        # The left/right limits are the two relay states at the same t.
        first = findfirst(==(switching[1]), times)
        @test state[first] == 0.0
        @test isapprox(state[first + 1], 1.0; atol = 1.0e-6)
        second = findfirst(==(switching[2]), times)
        @test isapprox(state[second], 1.0; atol = 1.0e-6)
        @test state[second + 1] == 0.0
    end

    @testset "Zenonian ball stops with W206" begin
        # The restitution 0.8 ball reaches the Zeno point at t ~ 4.06 s; running past it with
        # a small event_limit must stop at the limit, not run into MaxIters or crash.
        doc = _ev_model("EvZeno", _EV_BALL; t_end = 5.0, event_limit = 25, points = 501)
        result, dir, _ = _ev_run(doc)
        @test result.status == "done"
        @test result.stats.events > 25
        codes = [d.code for d in result.diagnostics]
        @test "W206" in codes
        @test !("E901" in codes)
        w206 = only([d for d in result.diagnostics if d.code == "W206"])
        @test w206.severity == "warning"
        @test occursin("event limit", w206.message)

        manifest = _ev_manifest(dir)
        mcode = [String(d.code) for d in manifest.diagnostics]
        @test "W206" in mcode
        @test Int(manifest.stats.events) > 25
        @test Int(manifest.time.n) > 0
        @test isfile(joinpath(dir, "stream.f64"))
        @test isfile(joinpath(dir, "columns.f64"))
    end

    @testset "nonsmooth conditions land on the kinks" begin
        doc = _ev_model("EvSmooth", _EV_SMOOTH; t_end = 4.5, points = 451,
            solver = "Tsit5", reltol = 1.0e-9, abstol = 1.0e-11)
        flat = _ev_flat(doc)
        @test isempty(_ev_errors(flat))
        conditions = BGSim.nonsmooth_conditions(flat)
        @test !isempty(conditions)
        shown = sprint(show, conditions)
        @test occursin("Plant/x", shown)
        # abs/sign at x = 0 and clamp at +-1, min at 2, max at -2: the kink times with
        # x(t) = -2 + t are 1, 2, 3 and 4 s.
        @test length(conditions) >= 4

        result, _, columns = _ev_run(doc)
        @test result.status == "done"
        groups = _ev_event_groups(columns["time"])
        for kink in (1.0, 2.0, 3.0, 4.0)
            @test any(abs(t - kink) <= 1.0e-5 for t in groups)
        end
        # Condition-only events have no affect; both limits are identical at the kink.
        t_kink = first(t for t in groups if abs(t - 2.0) <= 1.0e-5)
        left = findfirst(==(t_kink), columns["time"])
        right = findlast(==(t_kink), columns["time"])
        @test columns["Plant/x"][left] == columns["Plant/x"][right]
    end
end
