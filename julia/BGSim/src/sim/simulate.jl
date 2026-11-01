# The run loop (plan sections 5.8, 5.9 with the discrete scheduler, and 5.10/5.11).
#
# `simulate` owns one run end to end:
#
#   1. refuse a flat model that already has an error diagnostic (the worker reports it);
#   2. lower and compile it, through the structural cache (a parameter-only re-run only
#      remakes the problem — decision D4);
#   3. open the run folder: the running manifest with the full signal list (REQ-1), then the
#      stream;
#   4. step the integrator exactly to every output-grid time and every discrete tick, record a
#      row (or the left/right pair of a changed tick) and flush at the plan 5.10 cadence;
#   5. finish with `columns.f64` and the final manifest.
#
# Cancellation is an atomic flag checked before every integrator step and after every one.
# Progress is a callback `(t, rows)` throttled to 100 ms; phase notifications are `(name,
# t_s)` with the plan 3.6 phase names. Solver failures become E901 with the time, the retcode
# and the five largest states (plan 5.11); MTK's balance exceptions become E103 and anything
# else E900.

"""
    SimResult

The outcome of one run: the contract status (`done`, `failed` or `cancelled`), the run's
diagnostics, the manifest stats/time, and the run folder. `first_data_s` is the wall time
from entering `simulate` to the first recorded row — the plan 5.12 "to first data" metric.
`cache_hit` says whether the structural cache was reused.
"""
struct SimResult
    status::String
    diagnostics::Vector{Diagnostic}
    stats::NamedTuple
    signals::Vector{NamedTuple}
    time::NamedTuple
    manifest::Any
    run_dir::String
    first_data_s::Float64
    cache_hit::Bool
end

# ---------------------------------------------------------------------------------------
# Cancellation and notifications
# ---------------------------------------------------------------------------------------

_cancelled(::Nothing) = false
_cancelled(flag::Threads.Atomic{Bool}) = flag[]
_cancelled(flag::Base.RefValue{Bool}) = flag[]
_cancelled(callback::Function) = callback() === true

function _progress(callback, t::Float64, rows::Integer)
    callback === nothing && return nothing
    try
        callback(t, Int(rows))
    catch
        # A progress sink must never take the simulation down.
    end
    return nothing
end

function _phase(callback, name::AbstractString, t_s::Real)
    callback === nothing && return nothing
    try
        callback(String(name), Float64(t_s))
    catch
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Solver selection (plan 5.8)
# ---------------------------------------------------------------------------------------

"""
    solver_algorithm(name, model) -> OrdinaryDiffEq algorithm

`"auto"` picks `Rodas5P()` when the compiled problem has a non-identity mass matrix and
`Tsit5()` otherwise. The user may name `Rodas5P`, `Tsit5`, `FBDF` or `Vern7`; any other name
is rejected and becomes E901 in `simulate`.
"""
function solver_algorithm(name::AbstractString, model::CompiledModel)
    key = lowercase(strip(name))
    key == "auto" && return model.algebraic ? Rodas5P() : OrdinaryDiffEqTsit5.Tsit5()
    key == "rodas5p" && return Rodas5P()
    key == "tsit5" && return OrdinaryDiffEqTsit5.Tsit5()
    key == "fbdf" && return OrdinaryDiffEqBDF.FBDF()
    key == "vern7" && return OrdinaryDiffEqVerner.Vern7()
    throw(ArgumentError(
        "unknown solver `$name`; use auto, Rodas5P, Tsit5, FBDF or Vern7"
    ))
end

# ---------------------------------------------------------------------------------------
# Events, W206 and the `record_event` seam (plan 3.5, 5.8 and D14)
# ---------------------------------------------------------------------------------------

# A callback firing is counted by wrapping the compiled MTK affect. `terminate!` after the
# limit makes the integrator return `Terminated` from the `step!` that crossed it, so a Zeno
# chatter cannot run to `MaxIters`. The wrapper is installed with `remake(prob; callback=...)`
# because `init` merges callbacks instead of replacing the problem's callback.
#
# Only real affects are counted when a callback has one; a one-directional `@events` entry
# still detects its falling zero crossing but has an empty negative affect, which is not a
# firing (D19). A condition-only callback (both edges empty, the nonsmooth kinks) counts every
# crossing, because landing on the kink is exactly its purpose.
_is_empty_affect(a) = a === nothing || a === ModelingToolkit.ModelingToolkitBase.EMPTY_AFFECT

# The firings are also tallied per callback slot (the `continuous_events` order of the
# compiled system, see `_dbg_wrap`), so W206 can name the condition that chatters.
const EventTally = Dict{Int,Int}

function _counted_affect!(affect, counter::Base.RefValue{Int}, limit::Int, count::Bool,
    tally::EventTally = EventTally(), slot::Int = 0)
    count || return affect
    return function (integ)
        counter[] += 1
        tally[slot] = get(tally, slot, 0) + 1
        affect(integ)
        counter[] > limit && ModelingToolkit.SciMLBase.terminate!(integ)
        return nothing
    end
end

function _counted_affect!(affect, counter::Base.RefValue{Int}, limit::Int, ::Val{:vector},
    count::Bool)
    count || return affect
    return function (integ, idx)
        counter[] += 1
        affect(integ, idx)
        counter[] > limit && ModelingToolkit.SciMLBase.terminate!(integ)
        return nothing
    end
end

function _with_event_limit(
    cb::ModelingToolkit.SciMLBase.ContinuousCallback,
    counter::Base.RefValue{Int},
    limit::Int,
    tally::EventTally = EventTally(),
    next::Base.RefValue{Int} = Ref(0),
)
    next[] += 1
    slot = next[]
    real = !_is_empty_affect(cb.affect!) || !_is_empty_affect(cb.affect_neg!)
    count_pos = real ? !_is_empty_affect(cb.affect!) : true
    count_neg = real ? !_is_empty_affect(cb.affect_neg!) : true
    return ModelingToolkit.SciMLBase.ContinuousCallback(
        cb.condition,
        _counted_affect!(cb.affect!, counter, limit, count_pos, tally, slot),
        _counted_affect!(cb.affect_neg!, counter, limit, count_neg, tally, slot);
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

function _with_event_limit(
    cb::ModelingToolkit.SciMLBase.VectorContinuousCallback,
    counter::Base.RefValue{Int},
    limit::Int,
    tally::EventTally = EventTally(),
    next::Base.RefValue{Int} = Ref(0),
)
    va = cb.affect!
    base = next[]
    next[] += cb.len
    real = any(!_is_empty_affect(a) for a in va.affects) ||
           any(!_is_empty_affect(a) for a in va.affect_negs)
    affects = Any[
        _counted_affect!(a, counter, limit, real ? !_is_empty_affect(a) : true, tally, base + i)
        for (i, a) in enumerate(va.affects)
    ]
    affect_negs = Any[
        _counted_affect!(a, counter, limit, real ? !_is_empty_affect(a) : true, tally, base + i)
        for (i, a) in enumerate(va.affect_negs)
    ]
    wrapped_affect = ModelingToolkit.ModelingToolkitBase.VectorAffect(
        va.eq2affect, affects, affect_negs
    )
    return ModelingToolkit.SciMLBase.VectorContinuousCallback(
        cb.condition,
        wrapped_affect,
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

function _with_event_limit(
    cb::ModelingToolkit.SciMLBase.CallbackSet,
    counter::Base.RefValue{Int},
    limit::Int,
    tally::EventTally = EventTally(),
    next::Base.RefValue{Int} = Ref(0),
)
    continuous = [
        _with_event_limit(c, counter, limit, tally, next) for c in cb.continuous_callbacks
    ]
    return ModelingToolkit.SciMLBase.CallbackSet(continuous, collect(cb.discrete_callbacks))
end

_with_event_limit(cb, ::Base.RefValue{Int}, ::Int, args...) = cb

# ---------------------------------------------------------------------------------------
# StopSimulation and Assertion: the run monitors
# ---------------------------------------------------------------------------------------
#
# An instance of `stdlib:sources/StopSimulation` or `stdlib:sources/Assertion` (recognised by
# its library reference) ends the run when it triggers: its latched flag (`stopped`/`failed`,
# set by the block's exact event) is 1, or its margin `z` is positive. The flags are read
# after initialization, after every discrete tick and integrator step, and inside every event
# affect, where a trigger calls `terminate!` so the run ends at the event instant itself.
# A stop ends the run as "done" with W217; a failed assertion as "failed" with E902.

const STOP_BLOCK = "stdlib:sources/StopSimulation"
const ASSERT_BLOCK = "stdlib:sources/Assertion"

struct RunMonitor
    kind::Symbol      # :stop or :assert
    path::String
    node::String
    latch::Any        # getter of the latched flag
    margin::Any       # getter of `z`
end

function run_monitors(flat::Flat.FlatModel, model::CompiledModel)
    out = RunMonitor[]
    for inst in flat.instances
        kind = inst.ref == STOP_BLOCK ? :stop : inst.ref == ASSERT_BLOCK ? :assert : nothing
        kind === nothing && continue
        latch = get(model.vars, inst.path * (kind === :stop ? "/stopped" : "/failed"), nothing)
        margin = get(model.vars, inst.path * "/z", nothing)
        (latch === nothing || margin === nothing) && continue
        push!(out, RunMonitor(kind, inst.path, inst.node, getu(model.system, latch),
            getu(model.system, margin)))
    end
    return out
end

"""The first monitor that has triggered at the integrator's current state, or `nothing`."""
function monitor_hit(monitors::Vector{RunMonitor}, integ)
    for m in monitors
        (m.latch(integ) >= 0.5 || m.margin(integ) > 0.0) && return m
    end
    return nothing
end

function _monitor_diagnostic(m::RunMonitor, t)
    if m.kind === :stop
        return diag("W217", "the run was stopped by `$(m.path)` at t = $t";
            hint = "StopSimulation ends the run when its input rises above threshold",
            path = m.path, node = m.node, block = STOP_BLOCK)
    end
    return diag("E902", "assertion `$(m.path)` failed at t = $t";
        hint = "the input of the Assertion fell below its threshold",
        path = m.path, node = m.node, block = ASSERT_BLOCK)
end

# Wrap every event affect so that a monitor triggered by it ends the integration at the event
# instant (`terminate!` makes `step!` return there).
function _monitor_affect(affect, check)
    _is_empty_affect(affect) && return affect
    return function (integ, args...)
        affect(integ, args...)
        check(integ) && ModelingToolkit.SciMLBase.terminate!(integ)
        return nothing
    end
end

function _with_monitors(cb::ModelingToolkit.SciMLBase.ContinuousCallback, check)
    return ModelingToolkit.SciMLBase.ContinuousCallback(
        cb.condition,
        _monitor_affect(cb.affect!, check),
        _monitor_affect(cb.affect_neg!, check);
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

function _with_monitors(cb::ModelingToolkit.SciMLBase.VectorContinuousCallback, check)
    va = cb.affect!
    wrapped_affect = ModelingToolkit.ModelingToolkitBase.VectorAffect(
        va.eq2affect,
        Any[_monitor_affect(a, check) for a in va.affects],
        Any[_monitor_affect(a, check) for a in va.affect_negs],
    )
    return ModelingToolkit.SciMLBase.VectorContinuousCallback(
        cb.condition,
        wrapped_affect,
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

function _with_monitors(cb::ModelingToolkit.SciMLBase.CallbackSet, check)
    continuous = [_with_monitors(c, check) for c in cb.continuous_callbacks]
    return ModelingToolkit.SciMLBase.CallbackSet(continuous, collect(cb.discrete_callbacks))
end

_with_monitors(cb, check) = cb

_event_limit_reached(counter::Base.RefValue{Int}, limit::Int) = counter[] > limit

function _event_limit_diagnostic(flat::Flat.FlatModel, t, count::Int, limit::Int,
    tally::EventTally = EventTally(), system = nothing)
    return diag(
        "W206",
        "the event limit of $limit was reached at t = $t ($count firings)" *
        _chatter_note(tally, system, count);
        hint = "the model may chatter (a Zeno event); check the event conditions or raise `event_limit`",
        path = _last_path(flat),
    )
end

# The condition of the busiest callback slot, when it took most of the firings: the slot
# order is the `continuous_events` order of the compiled system.
function _chatter_note(tally::EventTally, system, count::Int)
    (isempty(tally) || system === nothing || count == 0) && return ""
    slot, n = reduce((a, b) -> a[2] >= b[2] ? a : b, collect(tally))
    n < count / 2 && return ""
    text = try
        cbs = ModelingToolkit.continuous_events(system)
        slot <= length(cbs) ? join(string.(ModelingToolkit.conditions(cbs[slot])), ", ") : ""
    catch
        ""
    end
    isempty(text) && return ""
    return "; $n of them by the condition `$(first(text, 200))`"
end

# ---------------------------------------------------------------------------------------
# Kinks on a step target
# ---------------------------------------------------------------------------------------
#
# The run loop stops the integrator exactly on every output-grid time and tick (a tstop). A
# switching root on such a stop, or a few ulps before it (a ramp ending at 10.0 + 0.05 on the
# grid time 10.05, a Step on a tick), traps the event handling: the root finder puts the event
# on the last float before the root, the rest of the step to the stop is an ulp or two, and the
# callback's repeat nudge (a fraction of that step) cannot get past the root, so the same
# condition fires again at the same t until W206 (the race car of examples/cars with a 0.05 s
# pedal ramp: 100 000 firings at t = 10.049999999999999).
#
# Before stepping to a target, the conditions are probed at the ends of a small window around
# it, with the current state (only conditions explicit in `t` change sign over so short a time).
# When one has its root inside the window at or before the target, the step goes a little past
# the target instead (1e-12 relative): the root lies inside the step, the event is handled with
# a normal remaining step, and the row of the target is written at the target time with the
# values just after it. A root after the target needs nothing: the next step starts before it.

struct KinkProbe
    callbacks::Vector{Any}
    lengths::Vector{Int}
    values::Vector{Float64}
    window::Float64
end

function _continuous_callbacks(cb)
    cb === nothing && return Any[]
    cb isa ModelingToolkit.SciMLBase.CallbackSet && return collect(Any, cb.continuous_callbacks)
    cb isa ModelingToolkit.SciMLBase.AbstractContinuousCallback && return Any[cb]
    return Any[]
end

function kink_probe(integ)
    # a model with no state runs on a `NullODEIntegrator`, which has no callbacks
    hasproperty(integ, :opts) || return nothing
    cbs = _continuous_callbacks(integ.opts.callback)
    isempty(cbs) && return nothing
    lengths = Int[cb isa ModelingToolkit.SciMLBase.VectorContinuousCallback ? cb.len : 1 for cb in cbs]
    abstol = maximum(Float64(cb.abstol) for cb in cbs)
    return KinkProbe(cbs, lengths, zeros(sum(lengths)), max(100.0 * abstol, 1.0e-13))
end

function _probe!(probe::KinkProbe, integ, t)
    k = 0
    for (cb, n) in zip(probe.callbacks, probe.lengths)
        if cb isa ModelingToolkit.SciMLBase.VectorContinuousCallback
            cb.condition(view(probe.values, (k + 1):(k + n)), integ.u, t, integ)
        else
            probe.values[k + 1] = cb.condition(integ.u, t, integ)
        end
        k += n
    end
    return probe.values
end

function _snap_target(probe, integ, tt::Float64)
    probe === nothing && return tt
    t0 = Float64(integ.t)
    window = max(64.0 * eps(abs(tt)), probe.window)
    lo, hi = tt - window, tt + window
    lo <= t0 && return tt
    try
        clo = copy(_probe!(probe, integ, lo))
        chi = copy(_probe!(probe, integ, tt))
        for j in eachindex(clo)
            sa = sign(clo[j])
            (sa == 0 || sign(chi[j]) == sa) && continue
            # the root is in (lo, tt]: step past the target
            return tt + max(2.0 * window, 1.0e-12 * max(1.0, abs(tt)))
        end
        return tt
    catch
        return tt
    end
end

# The event-record seam for J2.2: the scheduler's run loop may pass its own record_event
# callback; the default writes the row through J1.5's recorder. The callback signature is
# `record_event(t::Float64, side::Symbol, values::Vector{Float64})` with side `:left`/`:right`.
_record_event!(::Nothing, rec::Recorder, t, side::Symbol, values) =
    record_row!(rec, t, values)
_record_event!(record_event, ::Recorder, t, side::Symbol, values) =
    record_event(t, side, values)

# ONE in-place generated function for the whole signal list (PERF-1). Per-signal `getu`
# getters cost one generated function (and one JIT compile) per recorded signal, which was
# 60-90 % of every run on the 2000+ signal multibond models; a vector-valued `getu` shares the
# sub-expressions but builds its result with a 2000-argument `create_array` call (≈1 ms per
# row). `build_explicit_observed_function(...; return_inplace)` returns an in-place variant that
# fills a preallocated vector in a few microseconds, and `optlevel = 0` cuts its first-call
# compile by 2-10x while the per-row cost stays negligible.
struct SignalReader{F}
    fn::F
    buffer::Vector{Float64}
end

function _signal_reader(model::CompiledModel, symbols::Vector{Num})
    isempty(symbols) && return nothing
    fn = ModelingToolkit.build_explicit_observed_function(
        model.system, symbols;
        checkbounds = false, return_inplace = true,
        compiler_options = ModelingToolkit.CompilerOptions(optlevel = 0),
    )[2]
    return SignalReader(fn, zeros(Float64, length(symbols)))
end

_signal_values(::Nothing, integ) = Float64[]
function _signal_values(reader::SignalReader, integ)
    reader.fn(reader.buffer, integ.u, integ.p, integ.t)
    return copy(reader.buffer)
end

# Evaluate every recorded signal at the saved left/right state of an event instant. The
# saved `sol.u` vector holds the unknowns only; observed values are recomputed from it and
# the current parameters, exactly as the recorder reads them during the grid rows.
function _values_at_state!(integ, getters, state, t::Float64)
    saved_u = copy(integ.u)
    saved_t = integ.t
    try
        copyto!(integ.u, state)
        integ.t = t
        return _signal_values(getters, integ)
    finally
        copyto!(integ.u, saved_u)
        integ.t = saved_t
    end
end

"""    _record_new_events!(integ, rec, record_event, cursor, getters) -> new cursor

Every event instant is saved twice by the solver (`save_positions = [true, true]`), so each
new group of equal times in `sol.t` is one event: the first saved state is the left limit,
the last the right limit. Both rows are written at the same `t` (plan 3.5)."""
function _record_new_events!(integ, rec, record_event, cursor::Int, getters)
    times = integ.sol.t
    states = integ.sol.u
    n = length(times)
    n <= cursor && return cursor
    i = cursor + 1
    while i <= n
        j = i
        while j < n && times[j + 1] == times[i]
            j += 1
        end
        t = Float64(times[i])
        _record_event!(
            record_event, rec, t, :left,
            _values_at_state!(integ, getters, states[i], t),
        )
        _record_event!(
            record_event, rec, t, :right,
            _values_at_state!(integ, getters, states[j], t),
        )
        i = j + 1
    end
    return n
end

# ---------------------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------------------

_last_path(flat::Flat.FlatModel) =
    isempty(flat.instances) ? nothing : flat.instances[end].path

function _origin_source(origin::Flat.Origin)
    origin.block === nothing && return nothing
    origin.range === nothing && return nothing
    return SourceRef(source_kind(origin.block), origin.block, origin.range)
end

_safe_signal_name(x) = _var_name(x)

function _largest_states(integ, model::CompiledModel)
    unknowns = ModelingToolkit.unknowns(model.system)
    u = collect(integ.u)
    n = min(5, length(u))
    n == 0 && return ""
    order = sortperm(abs.(u); rev = true)[1:n]
    parts = String[]
    for i in order
        name = i <= length(unknowns) ? _safe_signal_name(unknowns[i]) : "state[$i]"
        push!(parts, string(name, " = ", u[i]))
    end
    return join(parts, ", ")
end

function _state_origin(flat::Flat.FlatModel, name::AbstractString)
    for v in flat.variables
        v.id == name && return v.origin
    end
    return nothing
end

# A failure right at the start of a run with storage elements in derivative causality: the
# usual cause is a dependent inertia next to a stiff compliance (a hub `Inertia` on the drive
# of a compliant `Revolute3D` follows the joint's stiff deflection rates), which the default
# compile cannot start. The remedy is the physical one: give the element its own state.
function _dependent_store_note(diagnostics, early::Bool)
    early || return ""
    w201 = [d for d in diagnostics if d.code == "W201"]
    isempty(w201) && return ""
    m = match(r"`([^`]+)`", first(w201).message)
    first_name = m === nothing ? something(first(w201).path, "?") : m.captures[1]
    return "; $(length(w201)) storage element(s) are in derivative causality (W201, first " *
           "`$(first_name)`): their rate is fixed by other states, and next to a stiff " *
           "compliance the run cannot start. Give the element its own state (a spring for " *
           "the gear or shaft stiffness between it and what drives it), lump it into the " *
           "body it moves with, or use a rigid joint (`Revolute3DRigid`, its `Ja` armature)"
end

function _solver_diagnostic(integ, model::CompiledModel, flat::Flat.FlatModel,
    diagnostics = Diagnostic[], early::Bool = false)
    retcode = integ.sol.retcode
    t = integ.t
    largest = _largest_states(integ, model)
    first_name = isempty(largest) ? nothing : first(split(first(split(largest, ", ")), " = "))
    origin = first_name === nothing ? nothing : _state_origin(flat, first_name)
    return diag(
        "E901",
        "the solver failed at t = $(t) (retcode = $(retcode))";
        hint = (isempty(largest) ? "no states were available" : "largest states: " * largest) *
               _dependent_store_note(diagnostics, early),
        path = origin === nothing ? nothing : origin.path,
        block = origin === nothing ? nothing : origin.block,
        source = origin === nothing ? nothing : _origin_source(origin),
    )
end

# ---------------------------------------------------------------------------------------
# A loop torn through a coefficient that is zero in this run (E903)
# ---------------------------------------------------------------------------------------
#
# Tearing solves an equation for one of its unknowns and divides by that unknown's
# coefficient. When the coefficient is a parameter expression (the `D` of `y ~ C*x + D*u`,
# the `k` of a Gain), MTK assumes it is not zero: parameter values are runtime values (D4),
# not structure. If the value *is* zero in this run, the torn system computes Inf/NaN and the
# run fails at t = 0 with an initialization error or E901. After such a failure this analysis
# looks for the division by a zero parameter coefficient and names it, and the algebraic loop
# it sits in, next to the generic diagnostic (never instead of it). It only runs after a
# failure, so a run that works never pays for it and a guarded division (inside `ifelse`) is
# never blamed. It only blames a direct-feedthrough coefficient of a signal block (see
# `_feedthrough_coefficient`): a zero divisor elsewhere (a geometric offset in a rigid
# mechanism with an index problem) is not what a user should change.

# Every denominator of `ex` outside `ifelse` branches: `a / b` gives `b`, `b^-k` gives `b`.
function _denominators!(out::Vector{Any}, ex)
    Symbolics.iscall(ex) || return out
    op = Symbolics.operation(ex)
    args = Symbolics.arguments(ex)
    if op === ifelse
        _denominators!(out, args[1])
        return out
    elseif op === (/)
        push!(out, args[2])
    elseif op === (^) && length(args) == 2
        k = Symbolics.value(args[2])
        k isa Real && k < 0 && push!(out, args[1])
    end
    for a in args
        _denominators!(out, a)
    end
    return out
end

# The value of a denominator that depends on run-constant parameters only, or `nothing`.
function _parameter_value(den, values::Dict{String,Float64})
    vars = Symbolics.get_variables(den)
    isempty(vars) && return nothing
    subs = Dict{Any,Any}()
    for v in vars
        ModelingToolkit.isparameter(v) || return nothing
        name = try
            _var_name(v)
        catch
            return nothing
        end
        value = get(values, name, nothing)
        value === nothing && return nothing
        subs[v] = value
    end
    x = Symbolics.value(Symbolics.substitute(den, subs))
    return x isa Real ? Float64(x) : nothing
end

# The names an AST expression refers to, without their indices (`P/x[1]` and `P/x` both give
# `P/x`): a generic walk over the expression's fields.
_base_name(s::AbstractString) = (i = findfirst('[', s); i === nothing ? String(s) : String(s[1:i-1]))

function _ast_names!(out::Set{String}, ex)
    if ex isa BGSim.Name
        push!(out, _base_name(String(ex.name)))
    elseif ex isa BGSim.Expr
        for f in fieldnames(typeof(ex))
            _ast_names!(out, getfield(ex, f))
        end
    elseif ex isa AbstractVector
        for x in ex
            _ast_names!(out, x)
        end
    end
    return out
end

# Is the parameter `param` a direct-feedthrough coefficient of the block at `path`: does it
# appear in one of the block's own equations together with one of its signal outputs and one
# of its signal inputs (`y ~ C*x + D*u`, `y ~ k*u`)? Only such a coefficient decides whether
# the block closes an algebraic loop. A parameter of a power element (the offset of a
# `FixedJoint2D`, a mass) can also end up as a divisor of the torn system, but there a zero
# is not the cause of the failure (an index problem is, DEC-MB-2), so E903 stays silent.
function _feedthrough_coefficient(flat::Flat.FlatModel, param::String, path::String)
    inputs = Set{String}()
    outputs = Set{String}()
    for v in flat.variables
        v.origin.path == path || continue
        v.kind === :input && push!(inputs, _base_name(v.id))
        v.kind === :output && push!(outputs, _base_name(v.id))
    end
    (isempty(inputs) || isempty(outputs)) && return false
    target = _base_name(param)
    for e in flat.equations
        e.origin.path == path || continue
        names = _ast_names!(Set{String}(), e.lhs)
        _ast_names!(names, e.rhs)
        target in names || continue
        any(in(names), inputs) && any(in(names), outputs) && return true
    end
    return false
end

# The E903 diagnostic as a list (empty or one), added next to the failure's own diagnostic.
function _zero_coefficient_diagnostics(model::CompiledModel, flat::Flat.FlatModel)
    found = try
        _find_zero_coefficient(model, flat)
    catch
        # The analysis only adds to a failure message; it must never replace it with a crash.
        nothing
    end
    return found === nothing ? Diagnostic[] : Diagnostic[found]
end

function _find_zero_coefficient(model::CompiledModel, flat::Flat.FlatModel)
    values = Dict{String,Float64}()
    discrete = Set{String}()
    for p in flat.parameters
        get(p.attrs, :kind, nothing) === :discrete && (push!(discrete, p.id); continue)
        p.value isa Real && (values[p.id] = Float64(p.value))
    end
    sys = model.system
    observed = ModelingToolkit.observed(sys)
    eqs = ModelingToolkit.equations(sys)
    # The unknowns a time instant does not know: observed and algebraic, never a state.
    states = Set{String}()
    for e in eqs
        lhs = Symbolics.unwrap(e.lhs)
        if Symbolics.iscall(lhs) && Symbolics.operation(lhs) isa Symbolics.Differential
            push!(states, _var_name(Symbolics.arguments(lhs)[1]))
        end
    end
    names_of(ex) = String[_var_name(v) for v in Symbolics.get_variables(ex)
                          if !ModelingToolkit.isparameter(v)]
    graph = Dict{String,Set{String}}()
    found = nothing
    for e in observed
        lhs = _var_name(Symbolics.unwrap(e.lhs))
        graph[lhs] = Set(n for n in names_of(e.rhs) if !(n in states))
        if found === nothing
            for den in _denominators!(Any[], Symbolics.unwrap(e.rhs))
                value = _parameter_value(den, values)
                if value !== nothing && (value == 0.0 || !isfinite(value))
                    found = (lhs, den, value)
                    break
                end
            end
        end
    end
    found === nothing && return nothing
    for e in eqs
        lhs = Symbolics.unwrap(e.lhs)
        Symbolics.iscall(lhs) && Symbolics.operation(lhs) isa Symbolics.Differential && continue
        members = Set(n for n in vcat(names_of(e.lhs), names_of(e.rhs)) if !(n in states))
        for n in members
            union!(get!(graph, n, Set{String}()), members)
        end
    end
    lhs, den, value = found
    reach(from) = begin
        seen = Set{String}()
        stack = collect(get(graph, from, Set{String}()))
        while !isempty(stack)
            n = pop!(stack)
            n in seen && continue
            push!(seen, n)
            append!(stack, collect(get(graph, n, Set{String}())))
        end
        seen
    end
    loop = String[n for n in reach(lhs) if lhs in reach(n)]
    origin_path(name) = begin
        o = _state_origin(flat, name)
        o === nothing ? nothing : o.path
    end
    blocks = String[p for p in (origin_path(n) for n in loop) if p !== nothing && !isempty(p)]
    den_vars = [v for v in Symbolics.get_variables(den) if ModelingToolkit.isparameter(v)]
    # One parameter (`-P/D` is the coefficient -D): name the parameter, not the expression.
    single = length(den_vars) == 1 ? _var_name(only(den_vars)) : nothing
    den_text = single !== nothing && get(values, single, NaN) == value ? single : string(den)
    owner = nothing
    for p in flat.parameters
        if !isempty(den_vars) && p.id == _var_name(first(den_vars))
            owner = p.origin
            break
        end
    end
    # Only a direct-feedthrough coefficient of a signal block is reported; any other zero
    # divisor leaves the failure to the generic diagnostic.
    (owner === nothing || owner.path === nothing) && return nothing
    any(v -> _feedthrough_coefficient(flat, _var_name(v), owner.path), den_vars) || return nothing
    # The equation torn through the coefficient belongs to the coefficient's block, so that
    # block is in the loop even when tearing folded its own variables away (`P/y` substituted
    # into `K/y ~ (… P/y …) / P/D` leaves only `K` and `E` in the variable graph).
    if !isempty(loop) && owner !== nothing && !isempty(owner.path)
        push!(blocks, owner.path)
    end
    sort!(unique!(blocks))
    what = value == 0.0 ? "which is 0 in this run" : "which is $(value) in this run"
    message = if isempty(loop)
        "`$(lhs)` is computed by dividing by `$(den_text)`, $(what)"
    else
        through = isempty(blocks) ? "" : " through " * join(("`$b`" for b in blocks), ", ")
        "the algebraic loop$(through) cannot be solved: the compiler solves it for `$(lhs)` " *
        "by dividing by `$(den_text)`, $(what)"
    end
    hint = isempty(loop) ?
        "give the coefficient a value other than zero" :
        "at this value the block with that coefficient has no direct feedthrough, but its " *
        "equations still say it may have one. Make that structural (StateSpace: leave the " *
        "constant D at 0; TransferFunction: a numerator degree m below the order n), or break " *
        "the loop with a block that has no direct feedthrough (an integrator, a filter, a UnitDelay)"
    return diag(
        "E903", message;
        hint = hint,
        path = owner === nothing ? _last_path(flat) : owner.path,
        block = owner === nothing ? nothing : owner.block,
        source = owner === nothing ? nothing : _origin_source(owner),
    )
end

function _compile_diagnostic(err, flat::Flat.FlatModel)
    if err isa ModelingToolkit.ExtraEquationsSystemException ||
       err isa ModelingToolkit.ExtraVariablesSystemException
        return diag(
            "E103",
            "the equation system could not be balanced";
            hint = sprint(showerror, err),
            path = _last_path(flat),
        )
    elseif err isa LowerError
        return diag(
            "E900",
            "internal compiler error while lowering `$(flat.name)`";
            hint = err.message,
            path = err.path === nothing ? _last_path(flat) : err.path,
            block = err.block,
            source = err.block === nothing || err.range === nothing ? nothing :
                     SourceRef(source_kind(err.block), err.block, err.range),
        )
    elseif err isa ArgumentError
        return diag("E901", err.msg; path = _last_path(flat))
    end
    return diag(
        "E900",
        "internal compiler error while lowering `$(flat.name)`";
        hint = sprint(showerror, err),
        path = _last_path(flat),
    )
end

function _initialization_diagnostic(err, flat::Flat.FlatModel)
    text = sprint(showerror, err)
    lowered = lowercase(text)
    if occursin("singular", lowered) || occursin("initial condition", lowered) ||
       occursin("initialization", lowered)
        return diag(
            "E103", "initial conditions are inconsistent"; hint = text,
            path = _last_path(flat),
        )
    end
    return diag(
        "E900", "internal compiler error while initializing `$(flat.name)`";
        hint = text, path = _last_path(flat),
    )
end

# ---------------------------------------------------------------------------------------
# Failing before the run loop
# ---------------------------------------------------------------------------------------

function _write_failed_manifest(flat, settings, run_dir, run_id, model_hash, diagnostics;
    states = flat.stats.states, equations = flat.stats.equations)
    mkpath(run_dir)
    manifest = _manifest(
        id = run_id,
        model = flat.name,
        model_hash = model_hash,
        status = "failed",
        settings = to_namedtuple(settings),
        stats = _zero_stats(states, equations),
        signals = signal_entries(flat.signals),
        time = (n = 0, t0 = settings.t_start, t1 = settings.t_end),
        diagnostics = _diag_entries(diagnostics),
    )
    write_manifest_atomic(joinpath(run_dir, "manifest.json"), manifest)
    return manifest
end

# ---------------------------------------------------------------------------------------
# The public entry point
# ---------------------------------------------------------------------------------------

"Benchmark hook (PERF-1): phase timings and solver statistics of the last `simulate`."
const LAST_PROFILE = Ref{Any}(nothing)

"""
    simulate(flat; run_dir, run_id, model_hash, settings, cancel, progress, phase,
             record_event) -> SimResult

Run the continuous model `flat` and write its run folder. See the file header for the run
loop and the plan sections it implements.

`record_event` is the J2.2 seam: when the discrete scheduler owns the run loop, it can pass
`record_event(t, side, values)` to receive each event instant twice (`side` is `:left` or
`:right`, both at the same `t`). The default is `nothing`, which writes both rows through the
recorder directly. A discrete tick that changes a held output uses the same seam, so a step
in a held value renders as a vertical edge too.

`inputs` (X-EX1) drives parameters from sampled trajectories, `Dict(id => (t, u))`: the
parameter holds `u[k]` on `[t[k], t[k+1])` (zero-order hold), changed after a discrete tick
at the same instant, as an FMU host sets its inputs between `doStep`s. An export marker's
input is the parameter `<marker>/value`. See `src/sim/inputs.jl`.
"""
function simulate(flat::Flat.FlatModel; debug = nothing, kwargs...)
    # M4 debug: a debug run (`debug = ctx::DebugCtx`, src/sim/debug.jl) is bracketed so its
    # context is always finished; with `debug = nothing` this is the normal run (DEC-M4-8).
    return _dbg_run(debug) do
        _simulate_flat(flat; debug = debug, kwargs...)
    end
end

function _simulate_flat(flat::Flat.FlatModel;
    run_dir::Union{AbstractString,Nothing} = nothing,
    run_id::Union{AbstractString,Nothing} = nothing,
    model_hash::Union{AbstractString,Nothing} = nothing,
    settings = RunSettings(),
    cancel = nothing,
    progress = nothing,
    phase = nothing,
    record_event = nothing,
    debug = nothing,
    parameter_schedule = nothing,
    manifest_extra = nothing,
    inputs = nothing,
)
    # X-EX1: parameters driven by a sampled trajectory (zero-order hold, src/sim/inputs.jl).
    driven = driven_inputs(flat, inputs)
    cancel = _dbg_cancel(debug, cancel)  # M4 debug:
    start_ns = time_ns()
    run_settings = settings isa RunSettings ? settings : RunSettings(settings)
    dir = run_dir === nothing ? mktempdir() : String(run_dir)
    mkpath(dir)
    id = run_id === nothing ? basename(dir) : String(run_id)
    hash = model_hash === nothing ? compile_key(flat) : String(model_hash)

    flat_diagnostics = collect(Diagnostic, flat.diagnostics)
    errors = [d for d in flat_diagnostics if d.severity == "error"]
    if !isempty(errors)
        manifest = _write_failed_manifest(
            flat, run_settings, dir, id, hash, flat_diagnostics
        )
        elapsed = (time_ns() - start_ns) / 1.0e9
        return SimResult(
            "failed", flat_diagnostics, manifest.stats, flat.signals, manifest.time,
            manifest, dir, elapsed, false,
        )
    end

    # REQ-1: the live run tail must see the full signal list while the run is still
    # compiling, not only once the integrator starts. Write the running manifest before the
    # CPU-heavy lowering; `open_recorder` rewrites it (still "running") with the exact state
    # and equation counts, and the final rewrite carries the outcome.
    running_manifest = _manifest(
        id = id,
        model = flat.name,
        model_hash = hash,
        status = "running",
        settings = to_namedtuple(run_settings),
        stats = _zero_stats(flat.stats.states, flat.stats.equations),
        signals = signal_entries(flat.signals),
        time = (n = 0, t0 = run_settings.t_start, t1 = run_settings.t_end),
        diagnostics = _diag_entries(flat_diagnostics),
    )
    # DASHBOARD_PLAN.md: the parameter overrides and schedule the run uses (src/sim/overrides.jl).
    manifest_extra === nothing || (running_manifest = merge(running_manifest, manifest_extra))
    write_manifest_atomic(joinpath(dir, "manifest.json"), running_manifest)
    _phase(phase, "mtkcompile", 0.0)

    compile_ns = time_ns()
    lowered = try
        lower_model(flat; t_start = run_settings.t_start, t_end = run_settings.t_end)
    catch err
        diagnostic = _compile_diagnostic(err, flat)
        diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
        manifest = _write_failed_manifest(
            flat, run_settings, dir, id, hash, diagnostics
        )
        elapsed = (time_ns() - start_ns) / 1.0e9
        return SimResult(
            "failed", diagnostics, manifest.stats, flat.signals, manifest.time, manifest,
            dir, elapsed, false,
        )
    end
    compile_s = (time_ns() - compile_ns) / 1.0e9

    # Plan 5.7 (second paragraph): after `mtkcompile`, a variable that appeared under `ddt`
    # but was not kept as a differential state is in derivative causality too. This is the
    # iconic-model counterpart of SCAP's W201, so it goes into the run's diagnostics before
    # the recorder opens (the live tail and the final manifest both show it).
    post_compile = Compile.post_compile_warnings(flat, lowered.model.system)
    if !isempty(post_compile)
        flat_diagnostics = sort_diagnostics(vcat(flat_diagnostics, post_compile))
    end

    # Plan 5.8 / W206: count every callback firing and stop a Zeno chatter at `event_limit`.
    # The wrapped callback is installed by remaking the problem, because `init` merges a
    # callback kwarg with the problem's own callbacks instead of replacing them.
    event_counter = Ref(0)
    event_tally = EventTally()
    solver_problem = lowered.problem
    # StopSimulation / Assertion: an event that triggers one ends the integration there.
    monitors = run_monitors(flat, lowered.model)
    if haskey(lowered.problem.kwargs, :callback)
        limited = _with_event_limit(
            lowered.problem.kwargs[:callback], event_counter, run_settings.event_limit,
            event_tally,
        )
        if !isempty(monitors)
            limited = _with_monitors(limited, integ -> monitor_hit(monitors, integ) !== nothing)
        end
        limited = _dbg_wrap_callback(debug, limited, flat)  # M4 debug:
        solver_problem = remake(lowered.problem; callback = limited)
    end

    extra_states = length(lowered.model.int_states)
    states = Int(flat.stats.states) + extra_states
    equations = Int(flat.stats.equations) + extra_states

    # FIX-M2-2 (NOTE-4 gap 3): a model with no continuous state is refused *up front* when it
    # has an `@events` affect. Condition-only callbacks are not installed for a stateless model
    # (see `lower_flat`: its values are exact functions of `t`), but an `@events` affect
    # changes a value and must not be dropped. MTK's compiled scalar condition reads `tmp[1]`
    # of the (empty) state cache, so letting the run start would surface a `BoundsError` as a
    # confusing E901("no states were available") at t = 1e-6. Name the requirement instead.
    # The compiled system counts too: index reduction can remove every flat state.
    stateless = states == 0 || isempty(ModelingToolkit.unknowns(lowered.model.system))
    if stateless && !isempty(flat.events)
        first_event = flat.events[1]
        diagnostic = diag(
            "E901",
            "`$(flat.name)` has no continuous state, so its `@events` affect cannot be solved";
            hint = "the solver's event root finder needs at least one state; add a state " *
                   "(for example an Integrator) or use a `@discrete` clocked update",
            path = first_event.origin.path,
            block = first_event.origin.block,
            source = _origin_source(first_event.origin),
        )
        diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
        manifest = _write_failed_manifest(
            flat, run_settings, dir, id, hash, diagnostics;
            states = states, equations = equations,
        )
        elapsed = (time_ns() - start_ns) / 1.0e9
        return SimResult(
            "failed", diagnostics, manifest.stats, flat.signals, manifest.time, manifest,
            dir, elapsed, lowered.cache_hit,
        )
    end

    alg = try
        solver_algorithm(run_settings.solver, lowered.model)
    catch err
        diagnostic = _compile_diagnostic(err, flat)
        diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
        manifest = _write_failed_manifest(
            flat, run_settings, dir, id, hash, diagnostics;
            states = states, equations = equations,
        )
        elapsed = (time_ns() - start_ns) / 1.0e9
        return SimResult(
            "failed", diagnostics, manifest.stats, flat.signals, manifest.time, manifest,
            dir, elapsed, lowered.cache_hit,
        )
    end

    grid = output_grid(run_settings)
    # Plan 5.9: compile the discrete partitions (generated step functions) and their exact
    # nanosecond tick grid before the integrator is initialised, so the tick times can be
    # passed as `tstops`. E104/E105 are compile-time diagnostics, so `flat` is already clean.
    schedule = nothing
    if !isempty(flat.discrete)
        schedule = try
            discrete_schedule(
                flat; t_start = run_settings.t_start, t_end = run_settings.t_end,
                debug = _dbg_hooks(debug),  # M4 debug: the statement-hook variant
            )
        catch err
            diagnostic = _compile_diagnostic(err, flat)
            diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
            manifest = _write_failed_manifest(
                flat, run_settings, dir, id, hash, diagnostics;
                states = states, equations = equations,
            )
            elapsed = (time_ns() - start_ns) / 1.0e9
            return SimResult(
                "failed", diagnostics, manifest.stats, flat.signals, manifest.time,
                manifest, dir, elapsed, lowered.cache_hit,
            )
        end
    end
    _phase(phase, "init", 0.0)
    rec = open_recorder(
        dir, id, flat.name, hash, run_settings, flat.signals, flat_diagnostics;
        capacity = length(grid), states = states, equations = equations,
        created = running_manifest.created,
    )
    manifest_extra === nothing || (rec.manifest = merge(rec.manifest, manifest_extra))

    solver_kwargs = (; abstol = run_settings.abstol, reltol = run_settings.reltol)
    if run_settings.max_step !== nothing
        solver_kwargs = merge(solver_kwargs, (; dtmax = run_settings.max_step))
    end
    init_kwargs = (;
        solver_kwargs..., save_everystep = false, save_start = false, save_end = false
    )
    # The tick times are not given as tstops up front: the run loop stops on every tick itself,
    # and steps past one that has a switching root on it (`_snap_target`), which a tstop at the
    # tick would undo.
    # F5.1 insertion point: the breakpoints of every CSV table the model reads are tstops.
    csv_stops = csv_model_tstops(flat, run_settings.t_start, run_settings.t_end)
    if !isempty(csv_stops)
        merged = haskey(init_kwargs, :tstops) ? vcat(init_kwargs.tstops, csv_stops) : csv_stops
        init_kwargs = merge(init_kwargs, (; tstops = sort!(unique!(Float64.(merged)))))
    end
    init_kwargs = _dbg_init_kwargs(debug, init_kwargs)  # M4 debug: the watch pool (src/sim/watch.jl)
    init_ns = time_ns()
    integ = try
        init(solver_problem, alg; init_kwargs...)
    catch err
        diagnostic = _initialization_diagnostic(err, flat)
        diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic],
            _zero_coefficient_diagnostics(lowered.model, flat)))
        stats = (
            compile_s = compile_s, sim_s = 0.0, steps = 0, events = 0,
            states = states, equations = equations,
        )
        manifest = finish_recorder!(rec, "failed", stats, diagnostics)
        elapsed = (time_ns() - start_ns) / 1.0e9
        return SimResult(
            "failed", diagnostics, stats, flat.signals, manifest.time, manifest, dir,
            elapsed, lowered.cache_hit,
        )
    end

    prof_init_s = (time_ns() - init_ns) / 1.0e9
    probe = kink_probe(integ)
    retcode = integ.sol.retcode
    if retcode == ReturnCode.InitialFailure
        diagnostic = diag(
            "E103", "initial conditions are inconsistent";
            hint = "the initialization returned $(retcode)", path = _last_path(flat),
        )
        diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic],
            _zero_coefficient_diagnostics(lowered.model, flat)))
        stats = (
            compile_s = compile_s, sim_s = 0.0, steps = 0, events = 0,
            states = states, equations = equations,
        )
        manifest = finish_recorder!(rec, "failed", stats, diagnostics)
        elapsed = (time_ns() - start_ns) / 1.0e9
        return SimResult(
            "failed", diagnostics, stats, flat.signals, manifest.time, manifest, dir,
            elapsed, lowered.cache_hit,
        )
    end

    # One getter per recorded signal. Parameters (discrete values in J2) are read with
    # `getp`, everything else with `getu`; `getu` returns a callable whose argument is the
    # integrator (NOTES.md, section "Observed values with getu").
    symbols = Num[]
    for s in flat.signals
        x = get(lowered.model.vars, String(s.id), nothing)
        if x === nothing
            # A held discrete output is an MTK parameter (D4), not an unknown.
            x = get(lowered.model.params, String(s.id), nothing)
        end
        x === nothing && begin
            diagnostic = diag(
                "E900", "the recorded signal `$(s.id)` has no lowered variable";
                path = s.path === nothing ? nothing : String(s.path),
            )
            diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
            stats = (
                compile_s = compile_s, sim_s = 0.0, steps = 0, events = 0,
                states = states, equations = equations,
            )
            manifest = finish_recorder!(rec, "failed", stats, diagnostics)
            elapsed = (time_ns() - start_ns) / 1.0e9
            return SimResult(
                "failed", diagnostics, stats, flat.signals, manifest.time, manifest, dir,
                elapsed, lowered.cache_hit,
            )
        end
        push!(symbols, x)
    end
    getters = _signal_reader(lowered.model, symbols)
    prof_values_ns = Ref(UInt64(0))
    prof_tick_ns = Ref(UInt64(0))
    prof_step_ns = Ref(UInt64(0))
    values = function ()
        t0 = time_ns()
        out = _signal_values(getters, integ)
        prof_values_ns[] += time_ns() - t0
        return out
    end

    # Plan 5.9: the discrete runtime (getters, held-value setter, generated steps). Built
    # before the first row so a failure leaves a failed manifest rather than a half run.
    run = nothing
    if schedule !== nothing
        run = try
            prepare_discrete!(schedule, lowered.model, integ, run_settings.t_start)
        catch err
            diagnostic = _compile_diagnostic(err, flat)
            diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
            stats = (
                compile_s = compile_s, sim_s = 0.0, steps = 0, events = 0,
                states = states, equations = equations,
            )
            manifest = finish_recorder!(rec, "failed", stats, diagnostics)
            elapsed = (time_ns() - start_ns) / 1.0e9
            return SimResult(
                "failed", diagnostics, stats, flat.signals, manifest.time, manifest, dir,
                elapsed, lowered.cache_hit,
            )
        end
    end
    targets = discrete_targets(grid, run)
    # DASHBOARD_PLAN.md: the timed parameter changes are loop targets of their own.
    live_steps = _LiveStep[]
    if parameter_schedule !== nothing && !isempty(parameter_schedule)
        live_steps = try
            _resolve_steps(parameter_schedule, lowered.model, integ)
        catch err
            err isa ArgumentError || rethrow()
            diagnostic = diag("E003", err.msg; hint = "a schedule can only set a block parameter")
            diagnostics = sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
            stats = (
                compile_s = compile_s, sim_s = 0.0, steps = 0, events = 0,
                states = states, equations = equations,
            )
            manifest = finish_recorder!(rec, "failed", stats, diagnostics)
            elapsed = (time_ns() - start_ns) / 1.0e9
            return SimResult(
                "failed", diagnostics, stats, flat.signals, manifest.time, manifest, dir,
                elapsed, lowered.cache_hit,
            )
        end
        targets = schedule_targets(targets, live_steps)
    end
    next_step = 1
    drive = nothing
    if !isempty(driven)
        drive = InputDrive(driven, lowered.model, integ)
        targets = merge_input_targets(
            targets, input_times(drive, run_settings.t_start, run_settings.t_end)
        )
        # Samples at or before t_start hold from the first row on.
        apply_inputs!(drive, integ, run_settings.t_start)
    end
    # M4 debug: the session holds the live run objects for the debug checkpoints and commands.
    session = _dbg_begin!(
        debug; run_id = id, settings = run_settings, flat = flat, lowered = lowered.model,
        integ = integ, rec = rec, getters = getters, run = run, schedule = schedule,
        targets = targets, record_event = record_event, event_counter = event_counter,
    )

    # Row zero. `init` has run the initialization, so the state at t_start is valid. A tick at
    # exactly `t_start` is the initial state, not an execution (the loop steps, then ticks).
    record_row!(rec, run_settings.t_start, values())
    flush_recorder!(rec)
    first_data_s = (time_ns() - start_ns) / 1.0e9
    _phase(phase, "simulate", 0.0)
    _progress(progress, run_settings.t_start, rec.nrows)
    _dbg_entry!(debug, session)  # M4 debug: pause on entry

    status = "done"
    diagnostic = nothing
    extra_diagnostics = Diagnostic[]   # E903 next to a failure at the start (never instead)
    loop_ns = time_ns()
    last_progress_ns = time_ns()
    # A changed tick off the output grid records a left and a right row of every signal. A
    # clock much faster than the grid (a 16 kHz current loop under a 1 ms grid) would write
    # gigabytes that way, so such rows are kept only a tenth of an output step apart; the
    # grid rows still carry the held values. A clock no faster than that (a 1 ms controller
    # under a 10 ms grid) records every change, as before.
    tick_row_gap = length(grid) > 1 ? 0.1 * minimum(diff(grid)) * (1 - 1.0e-9) : Inf
    last_tick_rows = -Inf
    last_flush_ns = time_ns()
    next_index = 1
    event_cursor = 0
    # StopSimulation / Assertion: checked at the start (and so after every tick) and after
    # every integrator step; the run ends at the instant the monitor triggered.
    function monitor_end!()
        isempty(monitors) && return false
        hit = monitor_hit(monitors, integ)
        hit === nothing && return false
        tm = Float64(integ.t)
        if rec.nrows == 0 || rec.columns[1][rec.nrows] < tm
            record_row!(rec, tm, values())
        end
        diagnostic = _monitor_diagnostic(hit, tm)
        status = hit.kind === :stop ? "done" : "failed"
        return true
    end
    while next_index <= length(targets)
        if _cancelled(cancel)
            status = "cancelled"
            break
        end
        monitor_end!() && break
        target = targets[next_index]
        tt = target.t
        tolerance = 1.0e-12 * max(1.0, abs(tt))
        if integ.t >= tt - tolerance
            # A discrete tick runs before the row for this instant is recorded, so the row
            # carries the state the continuous solver has at `tt` plus the new held outputs.
            changed = false
            tick_only = true    # nothing but a tick changed values at `tt`
            before = nothing
            if _steps_due(live_steps, next_step, tt)
                # A parameter step: the left limit is the state before it, the right limit
                # the state after it (and after a tick at the same instant).
                before = values()
                next_step = _apply_due_steps!(
                    live_steps, next_step, tt, integ, lowered.model.algebraic
                )
                changed = true
                tick_only = false
            end
            if target.tick && run !== nothing
                before === nothing && (before = values())
                tk0 = time_ns()
                changed = run_tick!(run, integ, tt, target.tick_index) || changed
                prof_tick_ns[] += time_ns() - tk0
            end
            # X-EX1: a driven input changes after the tick at the same instant, so the tick
            # sampled the value held before it (an FMU host sets inputs after its doStep).
            if drive !== nothing && inputs_due(drive, tt)
                before_inputs = before === nothing ? values() : nothing
                if apply_inputs!(drive, integ, tt)
                    before === nothing && (before = before_inputs)
                    changed = true
                    tick_only = false
                end
            end
            dense = changed && tick_only && !target.grid && tt - last_tick_rows < tick_row_gap
            if changed && !dense
                _record_event!(record_event, rec, tt, :left, before)
                _record_event!(record_event, rec, tt, :right, values())
                last_tick_rows = tt
            elseif target.grid
                record_row!(rec, tt, values())
            end
            next_index += 1
            now = time_ns()
            if now - last_progress_ns >= 100_000_000
                _progress(progress, tt, rec.nrows)
                last_progress_ns = now
            end
            if now - last_flush_ns >= 100_000_000
                flush_recorder!(rec)
                last_flush_ns = now
            end
            _dbg_target!(debug, session, target)  # M4 debug: tick checkpoint
            continue
        end
        # A switching root on or just before the target: step a little past it.
        next_t = _snap_target(probe, integ, tt)
        dt = next_t - integ.t
        if dt <= 0
            if target.grid
                record_row!(rec, tt, values())
            end
            next_index += 1
            continue
        end
        before = integ.t
        sp0 = time_ns()
        step_ok = _dbg_step!(debug, session, integ, next_t, event_cursor)  # M4 debug:
        prof_step_ns[] += time_ns() - sp0
        event_cursor = _dbg_cursor(debug, session, event_cursor)  # M4 debug:
        # Record every event instant that this step crossed, twice (left and right limits)
        # before the row for `tt` is written.
        event_cursor = _record_new_events!(
            integ, rec, record_event, event_cursor, getters
        )
        _dbg_sync_cursor!(debug, session, event_cursor)  # M4 debug: a statement pause follows
        monitor_end!() && break
        if _event_limit_reached(event_counter, run_settings.event_limit)
            diagnostic = _event_limit_diagnostic(
                flat, integ.t, event_counter[], run_settings.event_limit, event_tally,
                lowered.model.system,
            )
            status = "done"
            if _dbg_failure!(debug, session, diagnostic)  # M4 debug: pause before the end
                status = "cancelled"
                diagnostic = nothing
            end
            break
        end
        if !step_ok || !_ok_retcode(integ.sol.retcode)
            # A zero coefficient breaks the torn system from the first evaluation on, so it
            # only explains a failure at the start of the run.
            # It is added to the solver's own diagnostic, never in place of it.
            integ.t <= run_settings.t_start &&
                append!(extra_diagnostics, _zero_coefficient_diagnostics(lowered.model, flat))
            early = integ.t - run_settings.t_start <=
                    1.0e-3 * (run_settings.t_end - run_settings.t_start)
            diagnostic = _solver_diagnostic(integ, lowered.model, flat, flat_diagnostics, early)
            status = "failed"
            if _dbg_failure!(debug, session, diagnostic)  # M4 debug: pause before the end
                status = "cancelled"
                diagnostic = nothing
                empty!(extra_diagnostics)
            end
            break
        end
        if integ.t <= before && next_index <= length(targets)
            diagnostic = diag(
                "E901", "the solver made no progress at t = $(integ.t)";
                hint = "retcode = $(integ.sol.retcode)", path = _last_path(flat),
            )
            status = "failed"
            if _dbg_failure!(debug, session, diagnostic)  # M4 debug: pause before the end
                status = "cancelled"
                diagnostic = nothing
            end
            break
        end
        if _cancelled(cancel)
            status = "cancelled"
            break
        end
    end
    sim_s = (time_ns() - loop_ns) / 1.0e9
    LAST_PROFILE[] = (;
        init_s = prof_init_s, loop_s = sim_s, step_s = prof_step_ns[] / 1.0e9,
        tick_s = prof_tick_ns[] / 1.0e9, values_s = prof_values_ns[] / 1.0e9,
        stats = hasproperty(integ, :stats) ? integ.stats : nothing,  # a stateless model has a NullODEIntegrator
        ticks = run === nothing ? 0 : length(schedule.tick_times),
        targets = length(targets),
    )

    steps = try
        Int(integ.stats.naccept)
    catch
        0
    end
    stats = (
        compile_s = compile_s,
        sim_s = sim_s,
        steps = steps,
        events = event_counter[],
        states = states,
        equations = equations,
    )
    diagnostics = diagnostic === nothing ? flat_diagnostics :
                  sort_diagnostics(vcat(flat_diagnostics, [diagnostic], extra_diagnostics))
    _phase(phase, "write", integ.t)
    _dbg_finalize!(debug, session)  # M4 debug: the manifest keeps `debug`
    manifest = finish_recorder!(rec, status, stats, diagnostics)
    elapsed = (time_ns() - start_ns) / 1.0e9
    return SimResult(
        status, diagnostics, stats, flat.signals, manifest.time, manifest, dir,
        first_data_s, lowered.cache_hit,
    )
end

_ok_retcode(retcode) =
    retcode == ReturnCode.Success || retcode == ReturnCode.Default

"""
    simulate(model; project_dir = nothing, kwargs...) -> SimResult

Convenience entry point: parse and flatten a model document (a path, JSON text or a Dict)
and run it. The worker calls the `FlatModel` method after its own check pass, so it can
report the flatten diagnostics before starting a run.
"""
function simulate(model::Union{AbstractString,AbstractDict};
    project_dir = nothing, kwargs...)
    flat = Compile.flatten(IR.parse_model(model); project_dir = project_dir)
    return simulate(flat; kwargs...)
end
