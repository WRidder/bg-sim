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

const _EV_NEGATED = """
@block Negated begin
    @variables x::Real = -2.0
    @outputs y::Real
    @equations begin
        ddt(x) ~ 1.0
        y ~ ifelse(x >= 0, 1.0, 0.0) + ifelse(x < 0, 2.0, 0.0)
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
        # the busiest condition is named (the impact h ~ 0 takes nearly every firing)
        @test occursin("by the condition", w206.message)

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

    @testset "a condition and its negation are one kink" begin
        # `x >= 0` gives `x - 0` and `x < 0` gives `0 - x`: one condition-only callback, not
        # two (a pair of exactly negated callbacks trapped `step!` in the bridge example).
        doc = _ev_model("EvNegated", _EV_NEGATED; t_end = 4.0, points = 401,
            solver = "Tsit5", reltol = 1.0e-9, abstol = 1.0e-11)
        flat = _ev_flat(doc)
        @test isempty(_ev_errors(flat))
        conditions = BGSim.nonsmooth_conditions(flat)
        @test length(conditions) == 1
        result, _, columns = _ev_run(doc)
        @test result.status == "done"
        @test any(abs(t - 2.0) <= 1.0e-5 for t in _ev_event_groups(columns["time"]))
    end
end

# A switching root on an output-grid time or tick, or a few ulps before it (the ramp of the
# race car in examples/cars ending at 10.0 + 0.05 == 10.05 on the grid), trapped the event
# handling until W206: the event lands on the float before the root, the rest of the step to
# the stop is an ulp, and the repeat nudge cannot pass the root. The run loop now lands exactly
# on its targets, and steps a little past a target that has a root on or just before it.
@testset "step targets land exactly, and step past a root on the target" begin
    SB = BGSim.ModelingToolkit.SciMLBase
    a, b = 10.0, 0.05                       # the root -b - a + t == 0 at t = 10.05
    for vector in (false, true)
        cb = vector ?
             SB.VectorContinuousCallback((out, u, t, i) -> (out[1] = -b - a + t; out[2] = t - 3.0),
                 (i, k) -> nothing, 2) :
             SB.ContinuousCallback((u, t, i) -> -b - a + t, i -> nothing)
        prob = SB.ODEProblem((u, p, t) -> [1.0], [0.0], (0.0, 14.0); callback = cb)
        integ = SB.init(prob, BGSim.OrdinaryDiffEqTsit5.Tsit5())
        t0 = nextfloat(10.04, 3)
        @test BGSim._dbg_step!(nothing, nothing, integ, t0, 0)
        @test integ.t == t0                 # exactly on the target
        probe = BGSim.kink_probe(integ)
        for target in (a + b, nextfloat(a + b, 3))     # the root on / just before the target
            past = BGSim._snap_target(probe, integ, target)
            @test target < past <= target + 1.0e-10
        end
        @test BGSim._snap_target(probe, integ, prevfloat(a + b, 2)) == prevfloat(a + b, 2)
        @test BGSim._snap_target(probe, integ, 10.06) == 10.06          # no root nearby
        past = BGSim._snap_target(probe, integ, a + b)
        @test BGSim._dbg_step!(nothing, nothing, integ, past, 0)
        @test integ.t == past
        @test BGSim._dbg_step!(nothing, nothing, integ, 10.06, 0)
        @test integ.t == 10.06
    end
    @test BGSim._snap_target(nothing, nothing, 1.0) == 1.0
end

@testset "an early E901 with W201 explains the dependent storage element" begin
    w201 = BGSim.diag("W201",
        "`Arm/inertia/P[1]` appears under ddt but was not kept as a differential state; the DAE index is raised")
    note = BGSim._dependent_store_note([w201], true)
    @test occursin("`Arm/inertia/P[1]`", note)
    @test occursin("its own state", note)
    @test BGSim._dependent_store_note([w201], false) == ""        # a failure later in the run
    @test BGSim._dependent_store_note(BGSim.Diagnostic[], true) == ""
end

# A condition that reads only held values changes sign at a tick, never inside a solver step,
# and the root finder compares the condition at both ends of a step with the parameters the
# integrator has now, so it never saw the crossing (the fanuc-pick drop latch `zd > 0` with
# `zd ~ armed * held * (sep - d_drop) - ...`, `armed` and `held` @discrete values). The run
# loop now fires an event whose condition crosses zero across a jump (a tick, a driven input,
# a parameter step) at the jump itself.
const _EV_JUMP = """
@block JumpLatch begin
    @variables begin
        x::Real = 0.0
        hit::Real = 0.0
        down::Real = 0.0
        k::Real = -1.0
        n::Real = 0.0
    end
    @outputs begin
        y::Real
        z::Real
    end
    @discrete Ts = 0.01 begin
        n = n + 1
        k = ifelse(n >= 25 && n < 60, 1.0, -1.0)
    end
    @equations begin
        ddt(x) ~ 1.0
        ddt(hit) ~ 0.0
        ddt(down) ~ 0.0
        y ~ hit
        z ~ down
    end
    @events begin
        k > 0 => begin
            reinit(hit, hit + 1.0)
        end
        k < 0 => begin
            reinit(down, down + 1.0)
        end
    end
end
"""

# The left and the right row at an event instant `t`.
function _ev_rows_at(columns, id, t)
    rows = findall(x -> abs(x - t) <= 1.0e-12, columns["time"])
    return columns[id][rows]
end

@testset "an event fires when a discrete tick makes its condition cross zero" begin
    for solver in ("Rodas5P", "FBDF")
        doc = _ev_model("EvJump", _EV_JUMP; t_end = 1.0, points = 101, solver = solver,
            reltol = 1.0e-8, abstol = 1.0e-10)
        result, _, columns = _ev_run(doc)
        @test result.status == "done"
        # k steps to +1 at the tick t = 0.25 and back to -1 at t = 0.6: each latch fires once,
        # at its tick (left row before, right row after), and never again.
        @test result.stats.events == 2
        @test _ev_rows_at(columns, "Plant/k", 0.25) == [-1.0, 1.0]
        @test _ev_rows_at(columns, "Plant/y", 0.25) == [0.0, 1.0]
        @test _ev_rows_at(columns, "Plant/z", 0.6) == [0.0, 1.0]
        @test all(==(0.0), columns["Plant/y"][columns["time"] .< 0.25])
        # the latch states stay put after the event (FBDF to its tolerance: abstol 1e-10)
        @test maximum(abs.(columns["Plant/y"][columns["time"] .> 0.25] .- 1.0)) <= 1.0e-8
        @test maximum(abs.(columns["Plant/z"][columns["time"] .> 0.6] .- 1.0)) <= 1.0e-8
    end
end

# Five one-directional events whose conditions cross zero downward (no affect) within a few
# ulps of each other: a tool descends through the lip-loss gap of five cups (examples/fanuc-pick:
# five SuctionCups land together on a level carton). The root finder locates them one at a time,
# with steps cut to 1e-13 s and to zero length; FBDF kept the event times as history nodes (the
# same t twice: "dt was forced below floating point epsilon", retcode Unstable) or two of them
# fired in turn at the same instant until MaxIters. The offsets (in ulps of the gap) are cases
# that failed before the root guard (`_with_root_guard`).
const _EV_TOOL = """
@block Tool begin
    @parameters begin
        K::Real = 400.0
        c::Real = 6.0
        z_eq::Real = -0.01
    end
    @variables begin
        z::Real = 0.03
        w::Real = 0.0
    end
    @outputs zt::Real
    @equations begin
        ddt(z) ~ w
        ddt(w) ~ -K * (z - z_eq) - c * w - 50.0 * w * abs(w)
        zt ~ z
    end
end
"""

const _EV_LIP = """
@block Lip begin
    @inputs zt::Real
    @parameters begin
        off::Real = 0.0
        h_lost::Real = 0.002
    end
    @variables lost::Real = 0.0
    @outputs h::Real
    @equations begin
        h ~ zt - off
        ddt(lost) ~ 0.0
    end
    @events begin
        h > h_lost => begin
            reinit(lost, 1.0)
        end
    end
end
"""

function _ev_lips_model(offs; solver = "FBDF")
    doc = _ev_model("EvLips", _EV_TOOL; t_end = 0.4, points = 401, solver = solver,
        reltol = 1.0e-6, abstol = 1.0e-8)
    doc["diagram"]["nodes"][1]["name"] = "Tool"
    for (k, o) in enumerate(offs)
        push!(doc["diagram"]["nodes"], Dict{String,Any}(
            "id" => "c$k", "name" => "Cup$k",
            "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => _EV_LIP)),
            "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
            "params" => Dict{String,Any}("off" => o),
            "constants" => Dict{String,Any}(), "starts" => Dict{String,Any}()))
        push!(doc["diagram"]["connections"], Dict{String,Any}(
            "id" => "w$k", "kind" => "signal",
            "from" => Dict{String,Any}("node" => "n1", "port" => "zt"),
            "to" => Dict{String,Any}("node" => "c$k", "port" => "zt")))
    end
    return doc
end

@testset "near-simultaneous crossings without an affect: FBDF keeps going" begin
    u = eps(0.03)
    reference = nothing
    # Unstable without the guard: [9, 16, 11, 3, 3], [1, 0, 1, 7, 1]; MaxIters (ping-pong) with
    # the restart alone: [6, 10, 7, 14, 9], [9, 9, 15, 6, 7]
    for pattern in ([9, 16, 11, 3, 3], [6, 10, 7, 14, 9], [1, 0, 1, 7, 1], [9, 9, 15, 6, 7])
        result, _, columns = _ev_run(_ev_lips_model(pattern .* u))
        @test result.status == "done"
        @test !any(d -> d.code == "E901", result.diagnostics)
        @test columns["time"][end] == 0.4
        # the latches agree with each other and with a one-step method
        lost = [columns["Cup$k/lost"][end] for k in 1:5]
        @test all(==(lost[1]), lost)
        if reference === nothing
            _, _, ref = _ev_run(_ev_lips_model(pattern .* u; solver = "Rodas5P"))
            reference = (lost = ref["Cup1/lost"][end], z = ref["Tool/z"][end])
        end
        @test lost[1] == reference.lost
        @test isapprox(columns["Tool/z"][end], reference.z; atol = 1.0e-5)
    end
end

# Four switching conditions of one gait clock whose phase sums are rounded differently (the
# stance/swing `ifelse` of examples/spider: the order of the terms of `t/T + off - phi0 - ...`
# is not fixed by the symbolic layer, so the four legs of one group cross within an ulp of
# each other). When two of them share a left root with values more than 10 eps apart there,
# DiffEqBase's repeat nudge is not made and both fire again at the same t with zero-length
# steps until W206 (`_guard_nudge_reference!`). The offsets are in ulps of the phase; every
# pattern reached the event limit before the fix, at t = 4.00984, 4.56984 or 4.80984.
const _EV_GAIT = """
@block Gait begin
    @parameters begin
        T::Real = 0.8, [unit = "s"]
        w::Real = 40.0, [unit = "1/s"]
        duty::Real = 0.7
        phi0::Real = 0.0123
        o1::Real = 0.0
        o2::Real = 0.0
        o3::Real = 0.0
        o4::Real = 0.0
    end
    @variables begin
        x::Real = 0.0
        s1::Real = 0.0
        s2::Real = 0.0
        s3::Real = 0.0
        s4::Real = 0.0
    end
    @outputs y::Real
    @equations begin
        s1 ~ ifelse(cos(2.0 * pi * (t / T + o1 - phi0 - 0.5 * duty)) > cos(pi * duty), 1.0, 0.0)
        s2 ~ ifelse(cos(2.0 * pi * (t / T + o2 - phi0 - 0.5 * duty)) > cos(pi * duty), 1.0, 0.0)
        s3 ~ ifelse(cos(2.0 * pi * (t / T + o3 - phi0 - 0.5 * duty)) > cos(pi * duty), 1.0, 0.0)
        s4 ~ ifelse(cos(2.0 * pi * (t / T + o4 - phi0 - 0.5 * duty)) > cos(pi * duty), 1.0, 0.0)
        ddt(x) ~ -3.0 * x + s1 + s2 + s3 + s4 + sin(w * t)
        y ~ x
    end
end
"""

@testset "switches on one left root with different values do not fire again" begin
    u = eps(4.0)
    reference = nothing
    for pattern in ([0, 0, 0, 0], [0, -3, 4, -1], [0, 0, 2, 1], [2, 2, 1, 1], [-1, -1, -2, 4])
        doc = _ev_model("EvGait", _EV_GAIT; t_end = 5.0, points = 251, event_limit = 3000,
            reltol = 1.0e-6, abstol = 1.0e-8)
        for (k, o) in enumerate(pattern)
            doc["diagram"]["nodes"][1]["params"]["o$k"] = o * u
        end
        result, _, columns = _ev_run(doc)
        @test result.status == "done"
        @test !any(d -> d.code == "W206", result.diagnostics)
        @test columns["time"][end] == 5.0
        # 13 switch instants (0.00984 + 0.8 k and 0.56984 + 0.8 k), four conditions each, once
        @test result.stats.events == 52
        # after the last switch (t = 4.80984) every leg is in stance
        @test all(columns["Plant/s$k"][end] == 1.0 for k in 1:4)
        reference === nothing && (reference = columns["Plant/x"][end])
        @test isapprox(columns["Plant/x"][end], reference; atol = 1.0e-5)
    end
end

const _EV_INPUT_LATCH = """
@block InputLatch begin
    @inputs u::Real
    @variables begin
        x::Real = 0.0
        hit::Real = 0.0
    end
    @outputs y::Real
    @equations begin
        ddt(x) ~ 1.0
        ddt(hit) ~ 0.0
        y ~ hit
    end
    @events begin
        u > 0.5 => begin
            reinit(hit, hit + 1.0)
        end
    end
end
"""

@testset "an event fires when a driven input makes its condition cross zero" begin
    doc = _ev_model("EvInputJump", _EV_INPUT_LATCH; t_end = 0.5, points = 51)
    push!(doc["diagram"]["nodes"], Dict{String,Any}(
        "id" => "n0", "name" => "In",
        "block" => Dict{String,Any}("ref" => "stdlib:converters/ExportInput"),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}("value" => "0.0"),
        "constants" => Dict{String,Any}(), "starts" => Dict{String,Any}()))
    push!(doc["diagram"]["connections"], Dict{String,Any}(
        "id" => "c0", "kind" => "signal",
        "from" => Dict{String,Any}("node" => "n0", "port" => "y"),
        "to" => Dict{String,Any}("node" => "n1", "port" => "u")))
    flat = _ev_flat(doc)
    @test isempty(_ev_errors(flat))
    dir = mktempdir()
    result = simulate(flat; run_dir = dir, settings = BGSim.RunSettings(doc["settings"]),
        inputs = Dict("In/value" => (t = [0.0, 0.3], u = [0.0, 1.0])))
    @test result.status == "done"
    columns = _ev_columns(dir)
    @test result.stats.events == 1
    @test _ev_rows_at(columns, "Plant/y", 0.3) == [0.0, 1.0]
    @test columns["Plant/y"][end] == 1.0
end
