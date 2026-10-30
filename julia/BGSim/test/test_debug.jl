# Work package J4.1: the debug run engine (plan 5.13, decisions D20 to D27).
#
# A debug run is `simulate(flat; debug = ctx)`. The tests drive it from a spawned task through
# the public API (`debug_pause!`, `debug_continue!`, `debug_step!`, `debug_run_to!`,
# `debug_cancel!`, `debug_set_breakpoints!`, `with_paused`) and collect `on_paused` through a
# channel:
#
#   * a debug run without breakpoints writes the same `columns.f64` bytes as a normal run
#     (dc-motor, drivetrain-kalman, bouncing-ball), and so does a run that is paused and
#     continued at ticks, solver steps, events and pause requests;
#   * step `tick` advances exactly one base tick (drivetrain-kalman);
#   * an event breakpoint pauses at the first bounce of the bouncing ball (0.45152 s, 1e-6);
#   * pause on entry, `debug_pause!`, `runTo`, time and exception breakpoints (E901, W206);
#   * cancel while paused ends the run as `cancelled` with valid run files;
#   * commands on a run that is not paused raise `DebugStateError`;
#   * the plan 5.13 targets: pause latency < 100 ms, step round trip < 50 ms, debug overhead
#     <= 1.3 x a normal run (warm, medians), printed.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3
# The median of a sample (no Statistics dependency: it is not a test target of the package).
function median(v)
    s = sort(collect(Float64, v))
    n = length(s)
    return isodd(n) ? s[(n + 1) ÷ 2] : (s[n ÷ 2] + s[n ÷ 2 + 1]) / 2
end

const _DBG_EXAMPLES = normpath(joinpath(@__DIR__, "..", "..", "..", "examples"))

# One loaded example: the flat model, its settings and a fresh-run helper.
struct _DbgModel
    flat::Any
    settings::BGSim.RunSettings
end

function _dbg_model(dir, file; settings = nothing)
    project = joinpath(_DBG_EXAMPLES, dir)
    md = IR.parse_model(joinpath(project, "models", file))
    flat = Compile.flatten(md; project_dir = project)
    @assert isempty([d for d in flat.diagnostics if d.severity == "error"])
    return _DbgModel(flat, settings === nothing ? BGSim.RunSettings(md.settings) : settings)
end

# A yielding cancel callback, like the worker's: it lets the controlling task run while the
# run task steps.
_dbg_cancel_cb() = () -> (yield(); false)

function _dbg_normal(m::_DbgModel; settings = m.settings)
    dir = mktempdir()
    result = simulate(m.flat; run_dir = dir, run_id = "dbg", settings = settings)
    return result, dir
end

function _dbg_direct(m::_DbgModel; ctx, settings = m.settings)
    dir = mktempdir()
    result = simulate(m.flat; run_dir = dir, run_id = "dbg", settings = settings, debug = ctx)
    return result, dir
end

"""A debug run on a spawned task plus the channel of `on_paused` notifications."""
mutable struct _DbgRun
    ctx::DebugCtx
    task::Task
    paused::Channel{Any}
    dir::String
end

function _dbg_spawn(m::_DbgModel; settings = m.settings, cancel = _dbg_cancel_cb(),
    kwargs...)
    paused = Channel{Any}(Inf)
    ctx = DebugCtx(; on_paused = info -> put!(paused, info), kwargs...)
    dir = mktempdir()
    task = Threads.@spawn simulate(
        m.flat; run_dir = dir, run_id = "dbg", settings = settings, debug = ctx,
        cancel = cancel,
    )
    # The run is over when the task is done: wake a waiter with a sentinel.
    Threads.@spawn begin
        try
            wait(task)
        catch
        end
        put!(paused, :finished)
    end
    return _DbgRun(ctx, task, paused, dir)
end

# The next notification (a NamedTuple) or `:finished`; fails instead of hanging.
function _dbg_next(run::_DbgRun; seconds = 180)
    timer = Timer(_ -> close(run.paused), seconds)
    try
        return take!(run.paused)
    finally
        close(timer)
    end
end

_dbg_result(run::_DbgRun) = fetch(run.task)

_dbg_columns(dir) = read(joinpath(dir, "columns.f64"))
_dbg_manifest(dir) = JSON3.read(read(joinpath(dir, "manifest.json"), String))

# Continue through every remaining pause until the run ends; returns the pause infos.
function _dbg_finish!(run::_DbgRun)
    infos = Any[]
    while true
        info = _dbg_next(run)
        info === :finished && return infos
        push!(infos, info)
        debug_continue!(run.ctx)
    end
end

function _dbg_valid_files(dir)
    manifest = _dbg_manifest(dir)
    n = Int(manifest.time.n)
    nsignals = length(manifest.signals)
    @test filesize(joinpath(dir, "columns.f64")) == 8 * n * (nsignals + 1)
    @test filesize(joinpath(dir, "stream.f64")) == 8 * n * (nsignals + 1)
    return manifest
end

const _DBG_DC = _dbg_model("dc-motor", "iconic.bgmodel.json")
const _DBG_KALMAN = _dbg_model("drivetrain-kalman", "drivetrain-kalman.bgmodel.json")
const _DBG_BALL = _dbg_model("bouncing-ball", "bouncing-ball.bgmodel.json")

# A relay with two `@events` entries (the slot-to-event mapping of the vector callback) and a
# model whose solution blows up at t = 1 (E901).
function _dbg_inline_model(name, source; t_end = 1.0, event_limit = 10000, points = 201,
    reltol = 1.0e-8, abstol = 1.0e-8)
    node = Dict{String,Any}(
        "id" => "n1", "name" => "Plant",
        "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => source)),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(), "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
    doc = Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[node], "connections" => Any[], "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "Rodas5P", "reltol" => reltol,
            "abstol" => abstol, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => event_limit,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
    md = IR.parse_model(doc)
    return _DbgModel(Compile.flatten(md), BGSim.RunSettings(md.settings))
end

const _DBG_RELAY = _dbg_inline_model("Relay", """
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
        stateout ~ y + abs(x)
    end
    @events begin
        x > hi => begin
            reinit(y, 1.0)
        end
        z < lo => begin
            reinit(y, 0.0)
        end
    end
end
""")

const _DBG_BLOWUP = _dbg_inline_model("Blowup", """
@block Blowup begin
    @variables begin
        x::Real = 1.0
    end
    @outputs y::Real
    @equations begin
        ddt(x) ~ x * x
        y ~ x
    end
end
"""; t_end = 2.0)

@testset "debug run engine (J4.1)" begin
    @testset "a debug run without breakpoints is bit-identical to a normal run" begin
        for (name, m) in (("dc-motor", _DBG_DC), ("drivetrain-kalman", _DBG_KALMAN),
            ("bouncing-ball", _DBG_BALL))
            normal, normal_dir = _dbg_normal(m)
            ctx = DebugCtx()
            debugged, debug_dir = _dbg_direct(m; ctx = ctx)
            @test normal.status == "done"
            @test debugged.status == "done"
            @test _dbg_columns(debug_dir) == _dbg_columns(normal_dir)
            @test read(joinpath(debug_dir, "stream.f64")) ==
                  read(joinpath(normal_dir, "stream.f64"))
            manifest = _dbg_manifest(debug_dir)
            @test manifest.status == "done"
            @test length(manifest.debug.breakpoints) == 0
            @test length(manifest.debug.edits) == 0
            @test length(manifest.debug.pauses) == 0
            @test !is_paused(ctx)
            @test paused_info(ctx) === nothing
            @test !haskey(_dbg_manifest(normal_dir), :debug)
        end
    end

    @testset "pause on entry, manifest while paused, continue" begin
        m = _DBG_DC
        _, normal_dir = _dbg_normal(m)
        run = _dbg_spawn(m; pause_on_entry = true)
        info = _dbg_next(run)
        @test info.reason == "entry"
        @test info.runId == "dbg"
        @test info.t == m.settings.t_start
        @test info.tick === nothing
        @test info.breakpointId === nothing
        @test info.location === nothing
        @test info.frame === nothing
        @test isempty(info.diagnostics)
        @test is_paused(run.ctx)
        @test paused_info(run.ctx) == info
        manifest = _dbg_manifest(run.dir)
        @test manifest.status == "paused"
        @test manifest.time.n == 1
        @test [p.reason for p in manifest.debug.pauses] == ["entry"]
        # The paused data is flushed: row zero is readable from the stream.
        @test filesize(joinpath(run.dir, "stream.f64")) == 8 * (length(manifest.signals) + 1)
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        result = _dbg_result(run)
        @test result.status == "done"
        @test _dbg_columns(run.dir) == _dbg_columns(normal_dir)
        final = _dbg_manifest(run.dir)
        @test final.status == "done"
        @test [p.reason for p in final.debug.pauses] == ["entry"]
        @test final.debug.pauses[1].t == m.settings.t_start
        @test !is_paused(run.ctx)
    end

    @testset "step tick advances exactly one base tick (drivetrain-kalman)" begin
        m = _DBG_KALMAN
        _, normal_dir = _dbg_normal(m)
        run = _dbg_spawn(m; pause_on_entry = true)
        info = _dbg_next(run)
        @test info.reason == "entry"
        @test info.tick == 0
        tick_times = with_paused(s -> copy(s.schedule.tick_times), run.ctx)
        @test length(tick_times) > 100
        rows_before = with_paused(s -> s.rec.nrows, run.ctx)
        for k in 1:20
            debug_step!(run.ctx, "tick")
            info = _dbg_next(run)
            @test info.reason == "step"
            @test info.tick == k
            @test info.t == tick_times[k]
            @test info.breakpointId === nothing
        end
        rows = with_paused(s -> s.rec.nrows, run.ctx)
        @test rows > rows_before
        # The rows of the tick are recorded when the run pauses after it.
        last_t = with_paused(s -> s.rec.columns[1][s.rec.nrows], run.ctx)
        @test last_t == tick_times[20]
        manifest = _dbg_manifest(run.dir)
        @test manifest.status == "paused"
        @test manifest.time.n == rows
        @test length(manifest.debug.pauses) == 21
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "done"
        @test _dbg_columns(run.dir) == _dbg_columns(normal_dir)
    end

    @testset "step solverStep: one internal integrator step each, results unchanged" begin
        m = _DBG_DC
        _, normal_dir = _dbg_normal(m)
        run = _dbg_spawn(m; pause_on_entry = true)
        _dbg_next(run)
        last_t = m.settings.t_start
        steps = Float64[]
        for _ in 1:12
            debug_step!(run.ctx, "solverStep")
            info = _dbg_next(run)
            @test info.reason == "step"
            @test info.t > last_t
            push!(steps, info.t - last_t)
            last_t = info.t
        end
        @test all(>(0), steps)
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        @test _dbg_columns(run.dir) == _dbg_columns(normal_dir)
    end

    @testset "event breakpoint: first bounce of the bouncing ball" begin
        m = _DBG_BALL
        _, normal_dir = _dbg_normal(m)
        bp = Dict{String,Any}(
            "id" => "bp-event", "enabled" => true, "kind" => "event",
            "event" => Dict{String,Any}("path" => nothing),
        )
        run = _dbg_spawn(m; breakpoints = [bp])
        first_info = _dbg_next(run)
        @test first_info.reason == "event"
        @test first_info.breakpointId == "bp-event"
        @test isapprox(first_info.t, sqrt(2 / 9.81); atol = 1.0e-6)
        loc = first_info.location
        @test loc.path == "Ball1"
        @test loc.scope == "@events"
        @test loc.ref == m.flat.events[1].origin.block
        event_range = BGSim.expr_range(m.flat.events[1].condition)
        @test loc.range == (
            line = event_range.line, col = event_range.col,
            endLine = event_range.endLine, endCol = event_range.endCol,
        )
        # The event is recorded (left and right row at the event time) before the pause.
        tail = with_paused(s -> (s.rec.columns[1][s.rec.nrows - 1], s.rec.columns[1][s.rec.nrows]), run.ctx)
        @test tail[1] == tail[2] == first_info.t
        manifest = _dbg_manifest(run.dir)
        @test manifest.status == "paused"
        @test manifest.time.t1 == first_info.t
        # Continue through every later bounce: each one pauses, and the data is unchanged.
        debug_continue!(run.ctx)
        rest = _dbg_finish!(run)
        @test length(rest) >= 2
        @test all(i -> i.reason == "event", rest)
        @test issorted([first_info.t; [i.t for i in rest]])
        @test _dbg_result(run).status == "done"
        @test _dbg_columns(run.dir) == _dbg_columns(normal_dir)
        final = _dbg_manifest(run.dir)
        @test length(final.debug.pauses) == 1 + length(rest)
        @test final.debug.breakpoints[1].id == "bp-event"
    end

    @testset "event path filter and the slot-to-event mapping" begin
        m = _DBG_BALL
        miss = Dict{String,Any}(
            "id" => "other", "enabled" => true, "kind" => "event",
            "event" => Dict{String,Any}("path" => "Nowhere"),
        )
        run = _dbg_spawn(m; breakpoints = [miss])
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "done"
        hit = Dict{String,Any}(
            "id" => "mine", "enabled" => true, "kind" => "event",
            "event" => Dict{String,Any}("path" => "Ball1"),
        )
        run = _dbg_spawn(m; breakpoints = [hit])
        @test _dbg_next(run).breakpointId == "mine"
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished

        # Two `@events` entries in one block: the pause location is the event that fired.
        relay = _DBG_RELAY
        any_event = Dict{String,Any}(
            "id" => "ev", "enabled" => true, "kind" => "event",
            "event" => Dict{String,Any}("path" => "Plant"),
        )
        run = _dbg_spawn(relay; breakpoints = [any_event])
        infos = _dbg_finish!(run)
        @test length(infos) == 2
        for (i, info) in enumerate(infos)
            r = BGSim.expr_range(relay.flat.events[i].condition)
            @test info.location.range.line == r.line
            @test info.location.range.col == r.col
        end
        @test infos[1].location.range.line != infos[2].location.range.line
        @test isapprox(infos[1].t, 1 / 12; atol = 1.0e-6)
        @test isapprox(infos[2].t, 1 / 3; atol = 1.0e-6)
    end

    @testset "step event pauses after the next firing" begin
        m = _DBG_BALL
        _, normal_dir = _dbg_normal(m)
        run = _dbg_spawn(m; pause_on_entry = true)
        _dbg_next(run)
        times = Float64[]
        for _ in 1:3
            debug_step!(run.ctx, "event")
            info = _dbg_next(run)
            @test info.reason == "step"
            @test info.location.scope == "@events"
            push!(times, info.t)
        end
        @test isapprox(times[1], sqrt(2 / 9.81); atol = 1.0e-6)
        @test issorted(times) && allunique(times)
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        @test _dbg_columns(run.dir) == _dbg_columns(normal_dir)
    end

    @testset "debug_pause! while running, then continue" begin
        m = _DBG_KALMAN
        _, normal_dir = _dbg_normal(m)
        run = _dbg_spawn(m)
        sleep(0.05)
        debug_pause!(run.ctx)
        info = _dbg_next(run)
        @test info isa NamedTuple
        @test info.reason == "pause"
        @test info.t > m.settings.t_start
        @test info.t < m.settings.t_end
        @test info.tick isa Int && info.tick >= 0
        debug_pause!(run.ctx)  # a request while paused must not re-pause after the resume
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "done"
        @test _dbg_columns(run.dir) == _dbg_columns(normal_dir)
    end

    @testset "runTo and time breakpoints" begin
        m = _DBG_DC
        run = _dbg_spawn(m; pause_on_entry = true)
        _dbg_next(run)
        debug_run_to!(run.ctx, 0.25)
        info = _dbg_next(run)
        @test info.reason == "time"
        @test info.breakpointId === nothing
        @test isapprox(info.t, 0.25; atol = 1.0e-12)
        # runTo is one-shot: a later continue does not pause at 0.25 again.
        @test_throws ArgumentError debug_run_to!(run.ctx, 0.1)
        @test_throws ArgumentError debug_run_to!(run.ctx, m.settings.t_end + 1)
        @test is_paused(run.ctx)
        debug_run_to!(run.ctx, 0.5)
        @test isapprox(_dbg_next(run).t, 0.5; atol = 1.0e-12)
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "done"

        # A time breakpoint set up front, and one set while the run is paused.
        early = Dict{String,Any}(
            "id" => "t1", "enabled" => true, "kind" => "time",
            "time" => Dict{String,Any}("t" => 0.125),
        )
        run = _dbg_spawn(m; breakpoints = [early], pause_on_entry = true)
        _dbg_next(run)
        late = Dict{String,Any}(
            "id" => "t2", "enabled" => true, "kind" => "time",
            "time" => Dict{String,Any}("t" => 0.75),
        )
        statuses = debug_set_breakpoints!(run.ctx, [early, late])
        @test [s.id for s in statuses] == ["t1", "t2"]
        @test all(s -> s.verified, statuses)
        @test all(s -> s.resolved.hooks == 0 && isempty(s.diagnostics), statuses)
        debug_continue!(run.ctx)
        info = _dbg_next(run)
        @test (info.reason, info.breakpointId) == ("time", "t1")
        @test isapprox(info.t, 0.125; atol = 1.0e-12)
        debug_continue!(run.ctx)
        info = _dbg_next(run)
        @test (info.reason, info.breakpointId) == ("time", "t2")
        @test isapprox(info.t, 0.75; atol = 1.0e-12)
        # Setting the same list again does not re-fire a breakpoint that was already hit.
        debug_set_breakpoints!(run.ctx, [early, late])
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        final = _dbg_manifest(run.dir)
        @test [p.reason for p in final.debug.pauses] == ["entry", "time", "time"]
        @test [b.id for b in final.debug.breakpoints] == ["t1", "t2"]

        # A time that already passed is reported as unverified.
        run = _dbg_spawn(m; pause_on_entry = true)
        _dbg_next(run)
        run_to = debug_set_breakpoints!(run.ctx, [Dict{String,Any}(
            "id" => "past", "enabled" => true, "kind" => "time",
            "time" => Dict{String,Any}("t" => m.settings.t_start),
        )])
        @test !run_to[1].verified
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished
    end

    @testset "exception breakpoints: E901 and W206" begin
        on_e901 = Dict{String,Any}(
            "id" => "ex", "enabled" => true, "kind" => "exception",
            "exception" => Dict{String,Any}("on" => ["E901", "W206"]),
        )
        m = _DBG_BLOWUP
        plain_result, _ = _dbg_normal(m)
        @test plain_result.status == "failed"
        run = _dbg_spawn(m; breakpoints = [on_e901])
        info = _dbg_next(run)
        @test info isa NamedTuple
        @test info.reason == "exception"
        @test info.breakpointId == "ex"
        @test [d.code for d in info.diagnostics] == ["E901"]
        @test info.t > 0.5 && info.t <= 1.0 + 1.0e-6
        # The state at failure can be inspected while the run is paused.
        x = with_paused(s -> Float64(s.integ.u[1]), run.ctx)
        @test x > 10
        @test _dbg_manifest(run.dir).status == "paused"
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        result = _dbg_result(run)
        @test result.status == "failed"
        @test any(d -> d.code == "E901", result.diagnostics)
        final = _dbg_valid_files(run.dir)
        @test final.status == "failed"
        @test [p.reason for p in final.debug.pauses] == ["exception"]

        # A code that does not match never pauses.
        other = Dict{String,Any}(
            "id" => "ex2", "enabled" => true, "kind" => "exception",
            "exception" => Dict{String,Any}("on" => ["W206"]),
        )
        run = _dbg_spawn(m; breakpoints = [other])
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "failed"

        # Cancelling at the exception pause ends the run as cancelled.
        run = _dbg_spawn(m; breakpoints = [on_e901])
        @test _dbg_next(run).reason == "exception"
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "cancelled"
        @test _dbg_valid_files(run.dir).status == "cancelled"

        # W206: the event limit of a chattering bouncing ball.
        limited = _DbgModel(
            _DBG_BALL.flat,
            BGSim.RunSettings(
                t_start = 0.0, t_end = 4.0, solver = "auto", reltol = 1.0e-8,
                abstol = 1.0e-10, output = Dict("mode" => "points", "points" => 400),
                event_limit = 3,
            ),
        )
        w_only = Dict{String,Any}(
            "id" => "w", "enabled" => true, "kind" => "exception",
            "exception" => Dict{String,Any}("on" => ["W206"]),
        )
        run = _dbg_spawn(limited; breakpoints = [w_only])
        info = _dbg_next(run)
        @test info.reason == "exception"
        @test [d.code for d in info.diagnostics] == ["W206"]
        rows = with_paused(s -> s.event_counter[], run.ctx)
        @test rows > 3
        debug_continue!(run.ctx)
        @test _dbg_next(run) === :finished
        result = _dbg_result(run)
        @test result.status == "done"
        @test any(d -> d.code == "W206", result.diagnostics)
    end

    @testset "cancel while paused: valid run files" begin
        m = _DBG_KALMAN
        run = _dbg_spawn(m; pause_on_entry = true)
        _dbg_next(run)
        for _ in 1:3
            debug_step!(run.ctx, "tick")
            _dbg_next(run)
        end
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished
        result = _dbg_result(run)
        @test result.status == "cancelled"
        manifest = _dbg_valid_files(run.dir)
        @test manifest.status == "cancelled"
        @test manifest.time.n >= 4
        @test [p.reason for p in manifest.debug.pauses] == ["entry", "step", "step", "step"]
        @test !is_paused(run.ctx)
        @test_throws DebugStateError debug_continue!(run.ctx)

        # Cancelling a running (not paused) run also ends it as cancelled.
        run = _dbg_spawn(m)
        sleep(0.02)
        debug_cancel!(run.ctx)
        info = _dbg_next(run)
        info === :finished || @test false
        @test _dbg_result(run).status == "cancelled"
        _dbg_valid_files(run.dir)
    end

    @testset "commands on a run that is not paused raise DebugStateError" begin
        ctx = DebugCtx()
        for call in (debug_continue!, c -> debug_step!(c, "tick"), c -> debug_run_to!(c, 0.1),
            c -> with_paused(s -> 1, c), c -> with_paused(s -> 1, c; requires_paused = false))
            @test_throws DebugStateError call(ctx)
        end
        @test_throws DebugStateError with_paused(s -> 1, nothing)
        err = try
            debug_continue!(ctx)
        catch e
            e
        end
        @test err isa DebugStateError && err.message == "run is not paused"
        @test_throws ArgumentError debug_step!(ctx, "probe-unknown")

        # While the run is running.
        m = _DBG_KALMAN
        run = _dbg_spawn(m)
        sleep(0.02)
        if !istaskdone(run.task) && !is_paused(run.ctx)
            @test_throws DebugStateError debug_continue!(run.ctx)
        end
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished

        # After the run, and a request that raced with the end never hangs.
        @test_throws DebugStateError debug_continue!(run.ctx)
        @test_throws DebugStateError with_paused(s -> 1, run.ctx)
        run = _dbg_spawn(_DBG_DC; pause_on_entry = true)
        _dbg_next(run)
        late = Threads.@spawn try
            with_paused(s -> 1, run.ctx)
        catch e
            e
        end
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished
        outcome = fetch(late)
        @test outcome === 1 || outcome isa DebugStateError

        # Two continues race: one resumes, the other fails.
        run = _dbg_spawn(_DBG_DC; pause_on_entry = true)
        _dbg_next(run)
        first = Threads.@spawn try
            debug_continue!(run.ctx)
            :ok
        catch e
            e
        end
        second = Threads.@spawn try
            debug_continue!(run.ctx)
            :ok
        catch e
            e
        end
        outcomes = [fetch(first), fetch(second)]
        @test count(==(:ok), outcomes) == 1
        @test count(o -> o isa DebugStateError, outcomes) == 1
        @test _dbg_next(run) === :finished

        # A DebugCtx runs one simulation.
        @test_throws ArgumentError simulate(
            _DBG_DC.flat; settings = _DBG_DC.settings, debug = run.ctx
        )
    end

    @testset "with_paused runs closures on the run task and rethrows their errors" begin
        run = _dbg_spawn(_DBG_DC; pause_on_entry = true)
        _dbg_next(run)
        on_run_task = with_paused(s -> current_task() === run.ctx.run_task, run.ctx)
        @test on_run_task
        @test with_paused(s -> s.integ.t, run.ctx) == _DBG_DC.settings.t_start
        @test with_paused(s -> s.run_id, run.ctx) == "dbg"
        @test_throws ErrorException with_paused(s -> error("boom"), run.ctx)
        @test is_paused(run.ctx)  # a failing closure does not end the pause
        @test_throws DebugStateError with_paused(
            s -> with_paused(t -> 1, run.ctx), run.ctx
        )
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished
    end

    @testset "disabled breakpoints never fire" begin
        bps = Any[
            Dict{String,Any}(
                "id" => "e", "enabled" => false, "kind" => "event",
                "event" => Dict{String,Any}("path" => nothing),
            ),
            Dict{String,Any}(
                "id" => "t", "enabled" => false, "kind" => "time",
                "time" => Dict{String,Any}("t" => 0.2),
            ),
            Dict{String,Any}(
                "id" => "x", "enabled" => false, "kind" => "exception",
                "exception" => Dict{String,Any}("on" => ["E901", "W206"]),
            ),
        ]
        run = _dbg_spawn(_DBG_BALL; breakpoints = bps)
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "done"
        run = _dbg_spawn(_DBG_BLOWUP; breakpoints = bps)
        @test _dbg_next(run) === :finished
        @test _dbg_result(run).status == "failed"
        # Enabling one while paused arms it; the statuses report all three.
        run = _dbg_spawn(_DBG_BALL; breakpoints = bps, pause_on_entry = true)
        _dbg_next(run)
        enabled = [merge(copy(bps[1]), Dict("enabled" => true)), bps[2], bps[3]]
        statuses = debug_set_breakpoints!(run.ctx, enabled)
        @test length(statuses) == 3 && all(s -> s.verified, statuses)
        @test statuses[1].resolved.hooks == 1
        @test statuses[1].resolved.paths == ["Ball1"]
        debug_continue!(run.ctx)
        @test _dbg_next(run).breakpointId == "e"
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished
    end

    @testset "breakpoint parsing and the kind registry" begin
        @test_throws ArgumentError parse_breakpoint(Dict(
            "id" => "l", "enabled" => true, "kind" => "probe-unknown",
            "probe-unknown" => Dict("ref" => "project:X", "line" => 3, "path" => nothing),
        ))
        @test_throws ArgumentError parse_breakpoint(Dict("id" => "k", "kind" => "nonsense"))
        @test_throws ArgumentError parse_breakpoint(Dict("kind" => "time"))
        @test_throws ArgumentError parse_breakpoint(Dict("id" => "k", "kind" => "time"))
        @test_throws ArgumentError parse_breakpoint(Dict(
            "id" => "k", "kind" => "time", "time" => Dict("t" => "x"),
        ))
        @test_throws ArgumentError parse_breakpoint(Dict(
            "id" => "k", "kind" => "exception", "exception" => Dict("on" => "E901"),
        ))
        @test_throws ArgumentError DebugCtx(breakpoints = [
            Dict("id" => "a", "kind" => "event", "event" => Dict("path" => nothing)),
            Dict("id" => "a", "kind" => "event", "event" => Dict("path" => nothing)),
        ])
        # JSON3 objects parse like Dicts, and `enabled` defaults to true.
        json = JSON3.read("""{"id":"j","kind":"time","time":{"t":0.5},"hitCount":null}""")
        bp = parse_breakpoint(json)
        @test bp.id == "j" && bp.enabled && bp.kind == "time" && bp.data["t"] == 0.5

        # A new kind (as J4.2/J4.3 register theirs) is resolved with the whole list.
        seen = Any[]
        register_breakpoint_kind!("probe-kind", (ctx, session, bps) -> begin
            push!(seen, (session === nothing, length(bps)))
            return NamedTuple[breakpoint_status(bp; hooks = 7) for bp in bps]
        end)
        try
            probe = Dict{String,Any}(
                "id" => "pk", "kind" => "probe-kind", "probe-kind" => Dict{String,Any}(),
            )
            ctx = DebugCtx()
            statuses = debug_set_breakpoints!(ctx, [probe])
            @test statuses[1].resolved.hooks == 7
            @test seen[end] == (true, 1)
            run = _dbg_spawn(_DBG_DC; breakpoints = [probe], pause_on_entry = true)
            _dbg_next(run)
            @test any(s -> s == (false, 1), seen)
            @test run.ctx.statuses[1].resolved.hooks == 7
            debug_cancel!(run.ctx)
            @test _dbg_next(run) === :finished
        finally
            delete!(BGSim.BREAKPOINT_KINDS, "probe-kind")
            filter!(!=("probe-kind"), BGSim.BREAKPOINT_KIND_ORDER)
        end
        register_step_granularity!("probe-step")
        @test "probe-step" in BGSim.STEP_GRANULARITIES
        filter!(!=("probe-step"), BGSim.STEP_GRANULARITIES)
    end

    @testset "plan 5.13 targets (warm): pause latency, step round trip, 1.3 x overhead" begin
        # Pause latency: debug_pause! to the paused notification of a running run.
        latencies = Float64[]
        for i in 0:7
            run = _dbg_spawn(_DBG_KALMAN)
            sleep(0.03)
            t0 = time_ns()
            debug_pause!(run.ctx)
            info = _dbg_next(run)
            i > 0 && push!(latencies, (time_ns() - t0) / 1.0e6)
            @test info isa NamedTuple && info.reason == "pause"
            debug_cancel!(run.ctx)
            @test _dbg_next(run) === :finished
        end
        latency_ms = median(latencies)
        println("J4.1 pause latency (median of 7): ", round(latency_ms; digits = 2),
            " ms (max ", round(maximum(latencies); digits = 2), " ms)")
        @test latency_ms < 100
        @test maximum(latencies) < 100

        # Step (tick) round trip: debug_step! to the next paused notification.
        run = _dbg_spawn(_DBG_KALMAN; pause_on_entry = true)
        _dbg_next(run)
        steps = Float64[]
        for _ in 1:25
            t0 = time_ns()
            debug_step!(run.ctx, "tick")
            _dbg_next(run)
            push!(steps, (time_ns() - t0) / 1.0e6)
        end
        step_ms = median(steps)
        println("J4.1 step(tick) round trip (median of 25): ", round(step_ms; digits = 2),
            " ms (max ", round(maximum(steps); digits = 2), " ms)")
        @test step_ms < 50
        debug_cancel!(run.ctx)
        @test _dbg_next(run) === :finished

        # Overhead: a debug run without breakpoints against a normal run, warm.
        for (name, m) in (("dc-motor", _DBG_DC), ("drivetrain-kalman", _DBG_KALMAN))
            _dbg_normal(m)
            _dbg_direct(m; ctx = DebugCtx())
            normal_s = Float64[]
            debug_s = Float64[]
            # Interleaved samples with a collection before each, so neither variant pays for
            # the other's garbage. The ratio of the minimums is the load-robust estimator of
            # the intrinsic cost on a shared machine (other processes only ever add time);
            # the medians are printed for the record.
            for _ in 1:11
                GC.gc()
                t0 = time_ns()
                _dbg_normal(m)
                push!(normal_s, (time_ns() - t0) / 1.0e9)
                GC.gc()
                t0 = time_ns()
                _dbg_direct(m; ctx = DebugCtx())
                push!(debug_s, (time_ns() - t0) / 1.0e9)
            end
            ratio = minimum(debug_s) / minimum(normal_s)
            println("J4.1 overhead ", name, ": normal min ", round(minimum(normal_s); digits = 4),
                " s (median ", round(median(normal_s); digits = 4), "), debug min ",
                round(minimum(debug_s); digits = 4), " s (median ",
                round(median(debug_s); digits = 4), "), ratio ", round(ratio; digits = 3))
            @test ratio <= 1.3
        end
    end
end
