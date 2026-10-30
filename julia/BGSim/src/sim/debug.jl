# The debug run engine (plan sections 3.8 and 5.13, decisions D20 to D27; work package J4.1).
#
# A debug run is a normal run (`simulate`, plan 5.8 to 5.10) with a [`DebugCtx`](@ref)
# attached: `simulate(flat; ..., debug = ctx)`. With `debug = nothing` (the default) the run
# loop is exactly the code of a normal run (DEC-M4-8); every `# M4 debug:` insertion point in
# `simulate.jl` dispatches on the `debug` argument and the `Nothing` methods at the end of this
# file reproduce the original statements.
#
#   * The run task is the only task that touches the integrator. A pause blocks it on
#     `take!(ctx.commands)` (D23); every command ([`with_paused`](@ref)) is posted to the run
#     task and executed there with the live [`DebugSession`](@ref).
#   * Checkpoints: after every internal integrator step (`dbg_after_step!`), after every
#     tick/grid target (`_dbg_target!`), before a run ends on an error or W206
#     (`_dbg_exception!`) and on entry. Each checkpoint costs a few atomic loads and field
#     compares and does not yield.
#   * The debug step loop (`_dbg_step!`) replicates `SciMLBase.step!(integ, dt, true)` of
#     SciMLBase 7.21.4 (see NOTES.md) as an explicit loop of single `step!(integ)` calls, so the
#     checkpoint runs after each internal step while the numbers stay bit-identical.
#   * `@events` firings are detected by wrapping the problem's callback affects (the same way
#     `_with_event_limit` wraps them) and mapped to `flat.events` by their slot.
#
# Later work packages extend the engine without editing this file's loop: breakpoint kinds
# are a registry ([`register_breakpoint_kind!`](@ref)), step granularities are a registry
# ([`register_step_granularity!`](@ref)), commands are closures ([`with_paused`](@ref)), and the
# pause itself is [`dbg_pause!`](@ref).

import JSON3

"""
    DebugStateError(message)

Thrown by every debug command that needs a paused run (`run is not paused`) when the run is
running, finished, or not a debug run at all."""
struct DebugStateError <: Exception
    message::String
end

Base.showerror(io::IO, e::DebugStateError) = print(io, "DebugStateError: ", e.message)

# ---------------------------------------------------------------------------------------
# Breakpoints (plan 3.8)
# ---------------------------------------------------------------------------------------

"""
    Breakpoint(id, enabled, kind, data, condition, hit_count, raw)

A parsed plan 3.8 breakpoint. `data` is the kind's own object (`line`, `watch`, `time`,
`event` or `exception`) as plain `Dict`s; `raw` is the whole object, which the run manifest
stores in `debug.breakpoints`."""
struct Breakpoint
    id::String
    enabled::Bool
    kind::String
    data::Dict{String,Any}
    condition::Union{Nothing,String}
    hit_count::Union{Nothing,Int}
    raw::Dict{String,Any}
end

# Plain Julia containers from a Dict, a JSON3 object/array or anything already plain.
_plain(x::AbstractDict) = Dict{String,Any}(String(k) => _plain(v) for (k, v) in x)
_plain(x::AbstractVector) = Any[_plain(v) for v in x]
_plain(x) = x

struct BreakpointKind
    resolver::Any
    validate::Any
end

const BREAKPOINT_KINDS = Dict{String,BreakpointKind}()
const BREAKPOINT_KIND_ORDER = String[]

"""
    register_breakpoint_kind!(kind, resolver; validate = nothing)

Register how breakpoints of `kind` are parsed and resolved; J4.2 registers `"line"`, J4.3
`"watch"`. `parse_breakpoint` rejects every kind that is not registered with an
`ArgumentError`.

`resolver(ctx::DebugCtx, session::Union{Nothing,DebugSession}, bps::Vector{Breakpoint})`
is called with **all** breakpoints of that kind (disabled ones included; they must never fire)
every time the breakpoint list changes and once when the run starts. It returns one status per
breakpoint, in order (see [`breakpoint_status`](@ref)), and arms or disarms its own state from
scratch (it is also called with an empty list, so it can disarm). `session` is `nothing` when
the list is set before the run exists. `validate(data, raw)` may throw `ArgumentError` for a
malformed breakpoint object."""
function register_breakpoint_kind!(kind::AbstractString, resolver; validate = nothing)
    key = String(kind)
    haskey(BREAKPOINT_KINDS, key) || push!(BREAKPOINT_KIND_ORDER, key)
    BREAKPOINT_KINDS[key] = BreakpointKind(resolver, validate)
    return nothing
end

"""    breakpoint_status(bp; verified = true, hooks = 0, paths = String[], diagnostics = [])

One entry of the `debug.setBreakpoints` result (plan 3.8 `BreakpointStatus`)."""
breakpoint_status(bp::Breakpoint; verified::Bool = true, hooks::Integer = 0,
    paths = String[], diagnostics = Any[]) = (
    id = bp.id,
    verified = verified,
    resolved = (hooks = Int(hooks), paths = String[String(p) for p in paths]),
    diagnostics = collect(Any, diagnostics),
)

function _required(raw::Dict{String,Any}, key::String, what::String)
    haskey(raw, key) || throw(ArgumentError("a breakpoint needs `$key` ($what)"))
    return raw[key]
end

"""
    parse_breakpoint(x) -> Breakpoint

Parse a plan 3.8 breakpoint from a `Dict`, a JSON3 object or a [`Breakpoint`](@ref). An unknown
`kind` throws `ArgumentError("unsupported breakpoint kind …")`."""
function parse_breakpoint(x)
    x isa Breakpoint && return x
    raw = _plain(x)
    raw isa Dict{String,Any} || throw(ArgumentError("a breakpoint must be an object"))
    id = _required(raw, "id", "a string")
    id isa AbstractString && !isempty(id) ||
        throw(ArgumentError("a breakpoint `id` must be a non-empty string"))
    kind = _required(raw, "kind", "line, watch, time, event or exception")
    kind isa AbstractString || throw(ArgumentError("a breakpoint `kind` must be a string"))
    entry = get(BREAKPOINT_KINDS, String(kind), nothing)
    entry === nothing && throw(ArgumentError(
        "unsupported breakpoint kind `$kind` (supported: " *
        join(BREAKPOINT_KIND_ORDER, ", ") * ")"
    ))
    enabled = get(raw, "enabled", true)
    enabled isa Bool || throw(ArgumentError("breakpoint `$id`: `enabled` must be a boolean"))
    data = get(raw, String(kind), nothing)
    data isa Dict{String,Any} || throw(ArgumentError(
        "breakpoint `$id` of kind `$kind` needs a `$kind` object"
    ))
    condition = get(raw, "condition", nothing)
    condition === nothing || condition isa AbstractString || throw(ArgumentError(
        "breakpoint `$id`: `condition` must be a string or null"
    ))
    hit = get(raw, "hitCount", nothing)
    hit === nothing || (hit isa Integer && hit >= 1) || throw(ArgumentError(
        "breakpoint `$id`: `hitCount` must be a positive integer or null"
    ))
    entry.validate === nothing || entry.validate(data, raw)
    return Breakpoint(
        String(id), enabled, String(kind), data,
        condition === nothing ? nothing : String(condition),
        hit === nothing ? nothing : Int(hit), raw,
    )
end

function _parse_breakpoints(bps)
    out = Breakpoint[parse_breakpoint(bp) for bp in bps]
    ids = Set{String}()
    for bp in out
        bp.id in ids && throw(ArgumentError("duplicate breakpoint id `$(bp.id)`"))
        push!(ids, bp.id)
    end
    return out
end

# ---------------------------------------------------------------------------------------
# The context and the session
# ---------------------------------------------------------------------------------------

const _STATE_NEW = 0
const _STATE_RUNNING = 1
const _STATE_PAUSED = 2
const _STATE_FINISHED = 3

const STEP_GRANULARITIES = String["tick", "solverStep", "event"]

"""    register_step_granularity!(name)

Allow `debug_step!(ctx, name)`; J4.2 registers `"statement"`. The run sets `ctx.step_mode`
to `Symbol(name)` and resumes; the code that implements the granularity pauses (through
[`dbg_pause!`](@ref) with reason `"step"`) when it is reached."""
function register_step_granularity!(name::AbstractString)
    String(name) in STEP_GRANULARITIES || push!(STEP_GRANULARITIES, String(name))
    return nothing
end

mutable struct PendingCommand
    f::Any
    requires_paused::Bool
    done::Base.Event
    value::Any
    error::Any
end

struct WakeUp end

"""
    DebugCtx(; breakpoints = [], pause_on_entry = false, on_paused = nothing,
               on_resumed = nothing)

The debug context of one run (plan 5.13): the command channel, the atomic pause and cancel
flags, the breakpoint table, the step mode and the edits and pauses lists. Pass it as
`simulate(...; debug = ctx)` and control the run from another task with `debug_pause!`,
`debug_continue!`, `debug_step!`, `debug_run_to!`, `debug_cancel!`, `debug_set_breakpoints!`
and [`with_paused`](@ref). A context runs one simulation.

`on_paused(info)` receives the plan 3.8 `PausedInfo` as a NamedTuple `(runId, t, tick, reason,
breakpointId, location, frame, diagnostics)` on the run task, after the manifest says
`paused`; `on_resumed(run_id)` is called after continue, step and runTo. Neither may call
`with_paused` (it would wait for the task it runs on)."""
mutable struct DebugCtx
    breakpoints::Vector{Breakpoint}
    pause_on_entry::Bool
    on_paused::Any
    on_resumed::Any
    commands::Channel{Any}
    lock::ReentrantLock
    state::Threads.Atomic{Int}
    pending::Threads.Atomic{Int}
    pause_flag::Threads.Atomic{Bool}
    cancel_flag::Threads.Atomic{Bool}
    resume_requested::Bool
    step_mode::Symbol
    run_to::Float64
    next_time::Float64
    time_pending::Vector{Tuple{String,Float64}}
    time_fired::Set{Tuple{String,Float64}}
    event_bps::Vector{Breakpoint}
    exception_bps::Vector{Breakpoint}
    events::Vector{Any}
    fired::Vector{Int}
    pauses::Vector{NamedTuple{(:t, :reason),Tuple{Float64,String}}}
    edits::Vector{Any}
    statuses::Vector{Any}
    info::Any
    session::Any
    run_task::Union{Task,Nothing}
    ext::Dict{Symbol,Any}
end

function DebugCtx(; breakpoints = [], pause_on_entry::Bool = false, on_paused = nothing,
    on_resumed = nothing)
    return DebugCtx(
        _parse_breakpoints(breakpoints), pause_on_entry, on_paused, on_resumed,
        Channel{Any}(Inf), ReentrantLock(), Threads.Atomic{Int}(_STATE_NEW),
        Threads.Atomic{Int}(0), Threads.Atomic{Bool}(false), Threads.Atomic{Bool}(false),
        false, :none, Inf, Inf, Tuple{String,Float64}[], Set{Tuple{String,Float64}}(),
        Breakpoint[], Breakpoint[], Any[], Int[],
        NamedTuple{(:t, :reason),Tuple{Float64,String}}[], Any[], Any[], nothing, nothing,
        nothing, Dict{Symbol,Any}(),
    )
end

"""
    DebugSession

The live objects of a running debug run, handed to every [`with_paused`](@ref) closure and to
the checkpoints. All fields are only touched on the run task.

  * `ctx`, `run_id`, `settings` (`RunSettings`), `flat` (`Flat.FlatModel`), `lowered`
    (`CompiledModel`), `integ`, `rec` (`Recorder`), `getters` (one per recorded signal),
    `signal_ids` (their ids), `schedule` (`DiscreteSchedule` or `nothing`), `run`
    (`DiscreteRun` or `nothing`), `targets`, `record_event`, `event_counter` (`Ref{Int}`);
  * `tick`: ticks executed so far; `event_cursor`: the recorder's event cursor;
  * `info`: the current `PausedInfo` while paused."""
mutable struct DebugSession
    ctx::DebugCtx
    run_id::String
    settings::RunSettings
    flat::Any
    lowered::Any
    integ::Any
    rec::Recorder
    getters::Vector{Any}
    signal_ids::Vector{String}
    schedule::Any
    run::Any
    targets::Vector{RunTarget}
    record_event::Any
    event_counter::Base.RefValue{Int}
    tick::Int
    event_cursor::Int
    info::Any
end

# ---------------------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------------------

"""    is_paused(ctx) -> Bool"""
is_paused(ctx::DebugCtx) = ctx.state[] == _STATE_PAUSED

"""    paused_info(ctx) -> Union{Nothing,NamedTuple}

The current `PausedInfo` while the run is paused, `nothing` otherwise."""
paused_info(ctx::DebugCtx) = is_paused(ctx) ? ctx.info : nothing

_not_paused() = DebugStateError("run is not paused")

"""
    with_paused(f, ctx; requires_paused = true)

Run `f(session)` on the run task and return its value (an exception of `f` is rethrown
here). With `requires_paused = true` the run must be paused, otherwise a
`DebugStateError("run is not paused")` is thrown; with `false` the closure also runs at the
next checkpoint of a running run. Every pending and future command of a finished run fails with
the same error, so a request never hangs. Must not be called from the run task."""
function with_paused(f, ctx::DebugCtx; requires_paused::Bool = true)
    ctx.run_task === current_task() && throw(DebugStateError(
        "with_paused cannot be called from the run task"
    ))
    state = ctx.state[]
    (state == _STATE_NEW || state == _STATE_FINISHED ||
     (requires_paused && state != _STATE_PAUSED)) && throw(_not_paused())
    cmd = PendingCommand(f, requires_paused, Base.Event(), nothing, nothing)
    _post!(ctx, cmd)
    wait(cmd.done)
    cmd.error === nothing || throw(cmd.error)
    return cmd.value
end

with_paused(f, ::Nothing; requires_paused::Bool = true) = throw(_not_paused())

function _post!(ctx::DebugCtx, cmd)
    lock(ctx.lock) do
        ctx.state[] == _STATE_FINISHED && throw(_not_paused())
        Threads.atomic_add!(ctx.pending, 1)
        put!(ctx.commands, cmd)
    end
    return nothing
end

"""    request_resume!(session)

Inside a `with_paused` closure: leave the pause when the closure returns. `debug_continue!`
and `debug_step!` are this plus a step mode."""
function request_resume!(s::DebugSession)
    s.ctx.resume_requested = true
    s.ctx.pause_flag[] = false
    return nothing
end

"""    debug_pause!(ctx)

Ask the run to pause at its next checkpoint (an atomic flag, D23). Returns immediately; the
pause arrives as the `on_paused` notification with reason `"pause"`."""
function debug_pause!(ctx::DebugCtx)
    ctx.pause_flag[] = true
    return nothing
end

"""    debug_continue!(ctx)

Resume a paused run. Throws `DebugStateError` when it is not paused."""
function debug_continue!(ctx::DebugCtx)
    with_paused(ctx) do s
        ctx.step_mode = :none
        request_resume!(s)
        return nothing
    end
    return nothing
end

"""    debug_step!(ctx, granularity)

Resume a paused run until the next `"tick"` (after the next tick's partitions ran and its
rows were recorded; on a model without discrete partitions, the next output-grid time),
`"solverStep"` (after the next internal integrator step) or `"event"` (after the next
`@events` firing); the pause reason is `"step"`."""
function debug_step!(ctx::DebugCtx, granularity::AbstractString)
    String(granularity) in STEP_GRANULARITIES || throw(ArgumentError(
        "unsupported step granularity `$granularity` (supported: " *
        join(STEP_GRANULARITIES, ", ") * ")"
    ))
    with_paused(ctx) do s
        ctx.step_mode = Symbol(granularity)
        request_resume!(s)
        return nothing
    end
    return nothing
end

"""    debug_run_to!(ctx, t)

Resume a paused run until time `t` (a one-shot time breakpoint, reason `"time"`). `t` must
lie after the current time and not after `t_end`."""
function debug_run_to!(ctx::DebugCtx, t::Real)
    with_paused(ctx) do s
        target = Float64(t)
        target > s.integ.t || throw(ArgumentError(
            "runTo needs a time after the current time t = $(s.integ.t)"
        ))
        target <= s.settings.t_end || throw(ArgumentError(
            "runTo needs a time up to t_end = $(s.settings.t_end)"
        ))
        ctx.run_to = target
        ModelingToolkit.SciMLBase.add_tstop!(s.integ, target)
        _recompute_next_time!(ctx)
        ctx.step_mode = :none
        request_resume!(s)
        return nothing
    end
    return nothing
end

"""    debug_cancel!(ctx)

End the run as `cancelled`. Wakes a paused run; on a running run it is seen at the next
checkpoint. Never throws and never waits."""
function debug_cancel!(ctx::DebugCtx)
    ctx.cancel_flag[] = true
    lock(ctx.lock) do
        if ctx.state[] != _STATE_FINISHED
            Threads.atomic_add!(ctx.pending, 1)
            put!(ctx.commands, WakeUp())
        end
    end
    return nothing
end

"""
    debug_set_breakpoints!(ctx, bps) -> Vector{NamedTuple}

Replace the breakpoint list and return one status (`id`, `verified`, `resolved`,
`diagnostics`) per breakpoint. Works before the run starts, while it runs (applied at the
next checkpoint) and while paused. Throws `ArgumentError` for a malformed breakpoint or an
unsupported kind."""
function debug_set_breakpoints!(ctx::DebugCtx, bps)
    parsed = _parse_breakpoints(bps)
    early = lock(ctx.lock) do
        state = ctx.state[]
        state == _STATE_FINISHED && throw(_not_paused())
        if state == _STATE_NEW
            ctx.breakpoints = parsed
            _apply_breakpoints!(ctx, nothing)
            return ctx.statuses
        end
        return nothing
    end
    early === nothing || return early
    return with_paused(ctx; requires_paused = false) do s
        ctx.breakpoints = parsed
        _apply_breakpoints!(ctx, s)
        dbg_sync_manifest!(s)
        return ctx.statuses
    end
end

# ---------------------------------------------------------------------------------------
# Resolving the breakpoint table
# ---------------------------------------------------------------------------------------

function _apply_breakpoints!(ctx::DebugCtx, s::Union{Nothing,DebugSession})
    by_id = Dict{String,Any}()
    for kind in BREAKPOINT_KIND_ORDER
        bps = Breakpoint[bp for bp in ctx.breakpoints if bp.kind == kind]
        statuses = BREAKPOINT_KINDS[kind].resolver(ctx, s, bps)
        length(statuses) == length(bps) || error(
            "the `$kind` breakpoint resolver returned $(length(statuses)) statuses " *
            "for $(length(bps)) breakpoints"
        )
        for st in statuses
            by_id[st.id] = st
        end
    end
    ctx.statuses = Any[by_id[bp.id] for bp in ctx.breakpoints]
    _recompute_next_time!(ctx)
    return nothing
end

function _recompute_next_time!(ctx::DebugCtx)
    next = ctx.run_to
    for (_, t) in ctx.time_pending
        next = min(next, t)
    end
    ctx.next_time = next
    return nothing
end

# time: `add_tstop!` on the live integrator (right after `init` when set earlier).
function _resolve_time!(ctx::DebugCtx, s, bps::Vector{Breakpoint})
    empty!(ctx.time_pending)
    out = NamedTuple[]
    for bp in bps
        t = Float64(bp.data["t"])
        if s === nothing
            bp.enabled && push!(ctx.time_pending, (bp.id, t))
            push!(out, breakpoint_status(bp))
            continue
        end
        fired = (bp.id, t) in ctx.time_fired
        reachable = s.integ.t < t <= s.settings.t_end
        if bp.enabled && reachable && !fired
            push!(ctx.time_pending, (bp.id, t))
            ModelingToolkit.SciMLBase.add_tstop!(s.integ, t)
        end
        push!(out, breakpoint_status(bp; verified = reachable || fired))
    end
    return out
end

_path_matches(filter, path) = filter === nothing || (path !== nothing &&
    (path == filter || startswith(path, string(filter, "/"))))

# event: pause after an `@events` firing of the instance `event.path` (null: any).
function _resolve_event!(ctx::DebugCtx, s, bps::Vector{Breakpoint})
    ctx.event_bps = Breakpoint[bp for bp in bps if bp.enabled]
    out = NamedTuple[]
    events = s === nothing ? ctx.events : s.flat.events
    for bp in bps
        filter = get(bp.data, "path", nothing)
        matching = [
            e.origin.path for e in events if e isa Compile.FlatEvent &&
            !isempty(e.actions) && _path_matches(filter, e.origin.path)
        ]
        verified = s === nothing || !isempty(matching)
        push!(out, breakpoint_status(
            bp; verified = verified, hooks = length(matching), paths = unique(matching),
        ))
    end
    return out
end

# exception: pause before the run ends on one of the listed diagnostic codes.
function _resolve_exception!(ctx::DebugCtx, s, bps::Vector{Breakpoint})
    ctx.exception_bps = Breakpoint[bp for bp in bps if bp.enabled]
    return NamedTuple[breakpoint_status(bp) for bp in bps]
end

function _validate_time(data, raw)
    t = get(data, "t", nothing)
    t isa Real && isfinite(t) ||
        throw(ArgumentError("a time breakpoint needs a finite number `time.t`"))
    return nothing
end

function _validate_event(data, raw)
    path = get(data, "path", nothing)
    path === nothing || path isa AbstractString ||
        throw(ArgumentError("`event.path` must be a string or null"))
    return nothing
end

function _validate_exception(data, raw)
    on = get(data, "on", nothing)
    on isa AbstractVector && all(c -> c isa AbstractString, on) ||
        throw(ArgumentError("`exception.on` must be a list of diagnostic codes"))
    return nothing
end

register_breakpoint_kind!("time", _resolve_time!; validate = _validate_time)
register_breakpoint_kind!("event", _resolve_event!; validate = _validate_event)
register_breakpoint_kind!("exception", _resolve_exception!; validate = _validate_exception)

# ---------------------------------------------------------------------------------------
# Wrapping the `@events` affects
# ---------------------------------------------------------------------------------------

# The slot order of MTK's merged `VectorContinuousCallback` is the `continuous_events` order
# of the lowering: the `@events` entries in `flat.events` order, then the condition-only
# nonsmooth kinks (NOTES.md, J4.1). A slot `i <= length(flat.events)` whose entry has actions
# is an `@events` firing.
function _fire_marker(affect, fired::Vector{Int}, slot::Int)
    return function (integ)
        push!(fired, slot)
        affect(integ)
        return nothing
    end
end

_is_event_slot(events, slot::Int) = slot <= length(events) &&
    events[slot] isa Compile.FlatEvent && !isempty(events[slot].actions)

function _dbg_wrap(cb::ModelingToolkit.SciMLBase.ContinuousCallback, ctx::DebugCtx,
    next::Base.RefValue{Int})
    next[] += 1
    slot = next[]
    (_is_event_slot(ctx.events, slot) && !_is_empty_affect(cb.affect!)) || return cb
    return ModelingToolkit.SciMLBase.ContinuousCallback(
        cb.condition,
        _fire_marker(cb.affect!, ctx.fired, slot),
        cb.affect_neg!;
        initialize = cb.initialize,
        finalize = cb.finalize,
        idxs = cb.idxs,
        rootfind = cb.rootfind,
        interp_points = cb.interp_points,
        save_positions = cb.save_positions,
        dtrelax = cb.dtrelax,
        abstol = cb.abstol,
        reltol = cb.reltol,
        repeat_nudge = cb.repeat_nudge,
        initializealg = cb.initializealg,
        saved_clock_partitions = cb.saved_clock_partitions,
        maybe_discontinuity = cb.maybe_discontinuity,
        initialize_save_discretes = cb.initialize_save_discretes,
    )
end

function _dbg_wrap(cb::ModelingToolkit.SciMLBase.VectorContinuousCallback, ctx::DebugCtx,
    next::Base.RefValue{Int})
    va = cb.affect!
    base = next[]
    next[] += cb.len
    affects = Any[
        (_is_event_slot(ctx.events, base + i) && !_is_empty_affect(a)) ?
        _fire_marker(a, ctx.fired, base + i) : a for (i, a) in enumerate(va.affects)
    ]
    wrapped = ModelingToolkit.ModelingToolkitBase.VectorAffect(
        va.eq2affect, affects, collect(Any, va.affect_negs)
    )
    return ModelingToolkit.SciMLBase.VectorContinuousCallback(
        cb.condition,
        wrapped,
        cb.len;
        initialize = cb.initialize,
        finalize = cb.finalize,
        idxs = cb.idxs,
        rootfind = cb.rootfind,
        interp_points = cb.interp_points,
        save_positions = cb.save_positions,
        dtrelax = cb.dtrelax,
        abstol = cb.abstol,
        reltol = cb.reltol,
        repeat_nudge = cb.repeat_nudge,
        initializealg = cb.initializealg,
        saved_clock_partitions = cb.saved_clock_partitions,
        maybe_discontinuity = cb.maybe_discontinuity,
        initialize_save_discretes = cb.initialize_save_discretes,
    )
end

function _dbg_wrap(cb::ModelingToolkit.SciMLBase.CallbackSet, ctx::DebugCtx,
    next::Base.RefValue{Int})
    continuous = [_dbg_wrap(c, ctx, next) for c in cb.continuous_callbacks]
    return ModelingToolkit.SciMLBase.CallbackSet(continuous, collect(cb.discrete_callbacks))
end

_dbg_wrap(cb, ::DebugCtx, ::Base.RefValue{Int}) = cb

# ---------------------------------------------------------------------------------------
# The manifest of a debug run
# ---------------------------------------------------------------------------------------

_debug_info(ctx::DebugCtx) = (
    breakpoints = Any[bp.raw for bp in ctx.breakpoints],
    edits = copy(ctx.edits),
    pauses = [(t = p.t, reason = p.reason) for p in ctx.pauses],
)

function _write_debug_manifest!(s::DebugSession, status::AbstractString)
    rec = s.rec
    m = rec.manifest
    n = rec.nrows
    t0 = n == 0 ? m.time.t0 : rec.columns[1][1]
    t1 = n == 0 ? m.time.t1 : rec.columns[1][n]
    steps = try
        Int(s.integ.stats.naccept)
    catch
        0
    end
    stats = merge(m.stats, (steps = steps, events = s.event_counter[]))
    write_manifest_atomic(
        joinpath(rec.dir, "manifest.json"),
        merge(m, (
            status = String(status), stats = stats, time = (n = n, t0 = t0, t1 = t1),
            debug = _debug_info(s.ctx),
        )),
    )
    return nothing
end

"""    dbg_sync_manifest!(session)

Bring the manifest's `debug` section up to date (breakpoints, edits, pauses) and, when the run
is paused, rewrite the manifest file with status `paused`. J4.4 calls this after changing
`ctx.edits`."""
function dbg_sync_manifest!(s::DebugSession)
    s.rec.manifest = merge(s.rec.manifest, (debug = _debug_info(s.ctx),))
    s.ctx.state[] == _STATE_PAUSED && _write_debug_manifest!(s, "paused")
    return nothing
end

# ---------------------------------------------------------------------------------------
# Pausing
# ---------------------------------------------------------------------------------------

function _notify(callback, args...)
    callback === nothing && return nothing
    try
        callback(args...)
    catch err
        @warn "debug notification callback failed" exception = (err, catch_backtrace())
    end
    return nothing
end

function _run_command!(s::DebugSession, cmd::PendingCommand)
    try
        # `invokelatest`: the closure may be newer than the run task's world age.
        cmd.value = Base.invokelatest(cmd.f, s)
    catch err
        cmd.error = err
    end
    notify(cmd.done)
    return nothing
end

# Take one queued item. `cmd` is a `PendingCommand` or a `WakeUp`.
function _take_command!(ctx::DebugCtx)
    cmd = take!(ctx.commands)
    Threads.atomic_sub!(ctx.pending, 1)
    return cmd
end

# Commands that do not need a pause run at a checkpoint of a running run; the others fail.
function _drain_commands!(s::DebugSession)
    ctx = s.ctx
    while isready(ctx.commands)
        cmd = _take_command!(ctx)
        cmd isa PendingCommand || continue
        if cmd.requires_paused
            cmd.error = _not_paused()
            notify(cmd.done)
        else
            _run_command!(s, cmd)
        end
    end
    return nothing
end

"""
    dbg_pause!(session, reason; breakpoint_id = nothing, location = nothing, frame = nothing,
               diagnostics = []) -> Bool

Pause the run here (plan 5.13): record pending event rows, flush the recorder, rewrite the
manifest with status `paused`, call `on_paused` with the `PausedInfo` and block on the command
channel until a command resumes the run. Returns `true` after a resume (continue, step or
runTo) and `false` when the run was cancelled, which the caller must treat as "end the run":
`ctx.cancel_flag` is set and the checkpoints end the run as `cancelled` (a caller deep inside a
tick just finishes it; every later checkpoint is a no-op)."""
function dbg_pause!(s::DebugSession, reason::AbstractString; breakpoint_id = nothing,
    location = nothing, frame = nothing, diagnostics = Any[])
    ctx = s.ctx
    ctx.cancel_flag[] && return false
    # Event instants the last step crossed are recorded (left and right rows) before the
    # pause, so the paused data includes them and the cursor stays consistent.
    s.event_cursor = _record_new_events!(
        s.integ, s.rec, s.record_event, s.event_cursor, s.getters
    )
    flush_recorder!(s.rec)
    ctx.pause_flag[] = false
    ctx.step_mode = :none
    ctx.resume_requested = false
    t = Float64(s.integ.t)
    info = (
        runId = s.run_id,
        t = t,
        tick = s.run === nothing ? nothing : s.tick,
        reason = String(reason),
        breakpointId = breakpoint_id === nothing ? nothing : String(breakpoint_id),
        location = location,
        frame = frame,
        diagnostics = collect(Any, diagnostics),
    )
    push!(ctx.pauses, (t = t, reason = String(reason)))
    s.rec.manifest = merge(s.rec.manifest, (debug = _debug_info(ctx),))
    s.info = info
    ctx.info = info
    _write_debug_manifest!(s, "paused")
    ctx.state[] = _STATE_PAUSED
    _notify(ctx.on_paused, info)
    while !ctx.resume_requested && !ctx.cancel_flag[]
        cmd = _take_command!(ctx)
        cmd isa PendingCommand && _run_command!(s, cmd)
    end
    ctx.info = nothing
    s.info = nothing
    ctx.state[] = _STATE_RUNNING
    if ctx.cancel_flag[]
        return false
    end
    ctx.resume_requested = false
    _write_debug_manifest!(s, "running")
    _notify(ctx.on_resumed, s.run_id)
    return true
end

function _event_location(ev)
    r = ev.condition isa BGSim.Expr ? BGSim.expr_range(ev.condition) : ev.range
    return (
        path = something(ev.origin.path, ""),
        ref = something(ev.origin.block, ""),
        scope = "@events",
        range = (line = r.line, col = r.col, endLine = r.endLine, endCol = r.endCol),
    )
end

# ---------------------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------------------

# After every internal integrator step. Fast path: a few atomic loads and compares.
function dbg_after_step!(s::DebugSession)
    ctx = s.ctx
    ctx.pending[] > 0 && _drain_commands!(s)
    ctx.cancel_flag[] && return nothing
    integ = s.integ
    reason = nothing
    bp_id = nothing
    location = nothing
    if !isempty(ctx.fired)
        slot = 0
        for fired in ctx.fired
            for bp in ctx.event_bps
                if _path_matches(get(bp.data, "path", nothing), ctx.events[fired].origin.path)
                    slot = fired
                    bp_id = bp.id
                    break
                end
            end
            bp_id === nothing || break
        end
        if slot != 0
            reason = "event"
            location = _event_location(ctx.events[slot])
        elseif ctx.step_mode === :event
            reason = "step"
            location = _event_location(ctx.events[first(ctx.fired)])
        end
        empty!(ctx.fired)
    end
    if ctx.next_time < Inf &&
       integ.t >= ctx.next_time - 1.0e-12 * max(1.0, abs(ctx.next_time))
        timed = _consume_time!(ctx, integ.t)
        if reason === nothing
            reason = "time"
            bp_id = timed
        end
    end
    # M4 debug (J4.3): a watch crossing marked by the pool's affect (src/sim/watch.jl).
    watch = _watch_hit(ctx)
    if watch !== nothing && reason === nothing
        reason = "breakpoint"
        bp_id = watch.id
        location = watch.location
    end
    if reason === nothing && ctx.step_mode === :solverStep
        reason = "step"
    end
    if reason === nothing && ctx.pause_flag[]
        reason = "pause"
    end
    reason === nothing && return nothing
    dbg_pause!(s, reason; breakpoint_id = bp_id, location = location)
    return nothing
end

# Mark every time stop that `t` reached as done; returns the id of the first breakpoint hit.
function _consume_time!(ctx::DebugCtx, t::Float64)
    hit = nothing
    keep = Tuple{String,Float64}[]
    for (id, at) in ctx.time_pending
        if t >= at - 1.0e-12 * max(1.0, abs(at))
            push!(ctx.time_fired, (id, at))
            hit === nothing && (hit = id)
        else
            push!(keep, (id, at))
        end
    end
    ctx.time_pending = keep
    if t >= ctx.run_to - 1.0e-12 * max(1.0, abs(ctx.run_to))
        ctx.run_to = Inf
    end
    _recompute_next_time!(ctx)
    return hit
end

# After a tick/grid target was executed and its row recorded.
function _dbg_target!(ctx::DebugCtx, s::DebugSession, target::RunTarget)
    target.tick && (s.tick = target.tick_index)
    ctx.pending[] > 0 && _drain_commands!(s)
    ctx.cancel_flag[] && return nothing
    reason = nothing
    if ctx.step_mode === :tick && (target.tick || s.run === nothing)
        reason = "step"
    elseif ctx.pause_flag[]
        reason = "pause"
    end
    reason === nothing || dbg_pause!(s, reason)
    return nothing
end

# Before a run ends on a diagnostic (W206, E901): pause on a matching exception breakpoint
# so the state at failure can be inspected. Returns true when the run was cancelled while
# paused.
function _dbg_exception!(ctx::DebugCtx, s::DebugSession, diagnostic)
    ctx.cancel_flag[] && return true
    for bp in ctx.exception_bps
        if diagnostic.code in bp.data["on"]
            dbg_pause!(
                s, "exception"; breakpoint_id = bp.id,
                diagnostics = Any[to_namedtuple(diagnostic)],
            )
            break
        end
    end
    return ctx.cancel_flag[]
end

# ---------------------------------------------------------------------------------------
# The `# M4 debug:` insertion points of `simulate` (Nothing methods = the normal run)
# ---------------------------------------------------------------------------------------

# The public entry brackets a debug run so the context is always finished, and every pending
# or later command fails instead of hanging.
_dbg_run(f, ::Nothing) = f()

function _dbg_run(f, ctx::DebugCtx)
    lock(ctx.lock) do
        ctx.state[] == _STATE_NEW || throw(ArgumentError(
            "a DebugCtx runs one simulation; create a new one"
        ))
        ctx.run_task = current_task()
    end
    try
        return f()
    finally
        _dbg_finish!(ctx)
    end
end

function _dbg_finish!(ctx::DebugCtx)
    lock(ctx.lock) do
        ctx.state[] = _STATE_FINISHED
        ctx.info = nothing
        while isready(ctx.commands)
            cmd = take!(ctx.commands)
            Threads.atomic_sub!(ctx.pending, 1)
            if cmd isa PendingCommand
                cmd.error = _not_paused()
                notify(cmd.done)
            end
        end
    end
    return nothing
end

# The cancel callback of the run also sees `debug_cancel!`.
_dbg_cancel(::Nothing, cancel) = cancel
_dbg_cancel(ctx::DebugCtx, cancel) = () -> (ctx.cancel_flag[] || _cancelled(cancel))

_dbg_wrap_callback(::Nothing, cb, flat) = cb

function _dbg_wrap_callback(ctx::DebugCtx, cb, flat)
    ctx.events = Any[e for e in flat.events]
    return _dbg_wrap(cb, ctx, Ref(0))
end

_dbg_begin!(::Nothing; kwargs...) = nothing

function _dbg_begin!(ctx::DebugCtx; run_id, settings, flat, lowered, integ, rec, getters,
    run, schedule, targets, record_event, event_counter)
    s = DebugSession(
        ctx, String(run_id), settings, flat, lowered, integ, rec, Any[getters...],
        String[String(sig.id) for sig in flat.signals], schedule, run, targets,
        record_event, event_counter, 0, 0, nothing,
    )
    lock(ctx.lock) do
        ctx.session = s
        ctx.state[] = _STATE_RUNNING
        _apply_breakpoints!(ctx, s)
    end
    rec.manifest = merge(rec.manifest, (debug = _debug_info(ctx),))
    return s
end

# Pause on entry: after row zero, before the first step.
_dbg_entry!(::Nothing, ::Nothing) = nothing

function _dbg_entry!(ctx::DebugCtx, s::DebugSession)
    ctx.pause_on_entry && dbg_pause!(s, "entry")
    return nothing
end

_dbg_target!(::Nothing, ::Nothing, target) = nothing

# `SciMLBase.step!(integ, dt, stop_at_tdt = true)` of SciMLBase 7.21.4
# (src/integrator_interface.jl) as an explicit loop, with the checkpoint after each internal
# step. The `try` covers the same statements as in the normal run (the `add_tstop!` and the
# single steps), the checkpoint stays outside of it so a bug there is never reported as E901.
function _dbg_step!(::Nothing, ::Nothing, integ, dt, event_cursor)
    step_ok = try
        step!(integ, dt, true)
        true
    catch err
        false
    end
    return step_ok
end

function _dbg_step!(ctx::DebugCtx, s::DebugSession, integ, dt, event_cursor)
    s.event_cursor = event_cursor
    next_t = integ.t + dt
    ok = try
        (dt * integ.tdir) < 0 * oneunit(dt) && error("Cannot step backward.")
        ModelingToolkit.SciMLBase.add_tstop!(integ, next_t)
        true
    catch err
        false
    end
    ok || return false
    while integ.t * integ.tdir < next_t * integ.tdir
        ok = try
            step!(integ)
            true
        catch err
            false
        end
        ok || return false
        integ.sol.retcode in (ReturnCode.Default, ReturnCode.Success) || break
        dbg_after_step!(s)
        ctx.cancel_flag[] && break
    end
    return true
end

_dbg_cursor(::Nothing, ::Nothing, cursor) = cursor
_dbg_cursor(::DebugCtx, s::DebugSession, cursor) = s.event_cursor

# Before the run ends on a diagnostic. Returns true when the run was cancelled while paused.
_dbg_failure!(::Nothing, ::Nothing, diagnostic) = false
_dbg_failure!(ctx::DebugCtx, s::DebugSession, diagnostic) = _dbg_exception!(ctx, s, diagnostic)

# Refresh the manifest's debug section just before the final manifest is written.
_dbg_finalize!(::Nothing, ::Nothing) = nothing

function _dbg_finalize!(ctx::DebugCtx, s::DebugSession)
    s.rec.manifest = merge(s.rec.manifest, (debug = _debug_info(ctx),))
    return nothing
end

export DebugCtx, DebugSession, DebugStateError, Breakpoint
export debug_pause!, debug_continue!, debug_step!, debug_run_to!, debug_cancel!,
    debug_set_breakpoints!, is_paused, paused_info, with_paused, request_resume!,
    dbg_pause!, dbg_sync_manifest!, parse_breakpoint, register_breakpoint_kind!,
    register_step_granularity!, breakpoint_status
