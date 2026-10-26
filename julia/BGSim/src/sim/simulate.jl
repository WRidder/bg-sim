# The continuous run loop (plan sections 5.8, 5.9 without discrete parts, and 5.10/5.11).
#
# `simulate` owns one run end to end:
#
#   1. refuse a flat model that already has an error diagnostic (the worker reports it);
#   2. lower and compile it, through the structural cache (a parameter-only re-run only
#      remakes the problem — decision D4);
#   3. open the run folder: the running manifest with the full signal list (REQ-1), then the
#      stream;
#   4. step the integrator exactly to every output-grid time, record one row and flush at the
#      plan 5.10 cadence;
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

function _counted_affect!(affect, counter::Base.RefValue{Int}, limit::Int, count::Bool)
    count || return affect
    return function (integ)
        counter[] += 1
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
)
    real = !_is_empty_affect(cb.affect!) || !_is_empty_affect(cb.affect_neg!)
    count_pos = real ? !_is_empty_affect(cb.affect!) : true
    count_neg = real ? !_is_empty_affect(cb.affect_neg!) : true
    return ModelingToolkit.SciMLBase.ContinuousCallback(
        cb.condition,
        _counted_affect!(cb.affect!, counter, limit, count_pos),
        _counted_affect!(cb.affect_neg!, counter, limit, count_neg);
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
)
    va = cb.affect!
    real = any(!_is_empty_affect(a) for a in va.affects) ||
           any(!_is_empty_affect(a) for a in va.affect_negs)
    affects = Any[
        _counted_affect!(a, counter, limit, real ? !_is_empty_affect(a) : true) for
        a in va.affects
    ]
    affect_negs = Any[
        _counted_affect!(a, counter, limit, real ? !_is_empty_affect(a) : true) for
        a in va.affect_negs
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
)
    continuous = [
        _with_event_limit(c, counter, limit) for c in cb.continuous_callbacks
    ]
    return ModelingToolkit.SciMLBase.CallbackSet(continuous, collect(cb.discrete_callbacks))
end

_with_event_limit(cb, ::Base.RefValue{Int}, ::Int) = cb

_event_limit_reached(counter::Base.RefValue{Int}, limit::Int) = counter[] > limit

function _event_limit_diagnostic(flat::Flat.FlatModel, t, count::Int, limit::Int)
    return diag(
        "W206",
        "the event limit of $limit was reached at t = $t ($count firings)";
        hint = "the model may chatter (a Zeno event); check the event conditions or raise `event_limit`",
        path = _last_path(flat),
    )
end

# The event-record seam for J2.2: the scheduler's run loop may pass its own record_event
# callback; the default writes the row through J1.5's recorder. The callback signature is
# `record_event(t::Float64, side::Symbol, values::Vector{Float64})` with side `:left`/`:right`.
_record_event!(::Nothing, rec::Recorder, t, side::Symbol, values) =
    record_row!(rec, t, values)
_record_event!(record_event, ::Recorder, t, side::Symbol, values) =
    record_event(t, side, values)

# Evaluate every recorded signal at the saved left/right state of an event instant. The
# saved `sol.u` vector holds the unknowns only; observed values are recomputed from it and
# the current parameters, exactly as the recorder reads them during the grid rows.
function _values_at_state!(integ, getters, state, t::Float64)
    saved_u = copy(integ.u)
    saved_t = integ.t
    try
        copyto!(integ.u, state)
        integ.t = t
        return Float64[Float64(getter(integ)) for getter in getters]
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

function _solver_diagnostic(integ, model::CompiledModel, flat::Flat.FlatModel)
    retcode = integ.sol.retcode
    t = integ.t
    largest = _largest_states(integ, model)
    first_name = isempty(largest) ? nothing : first(split(first(split(largest, ", ")), " = "))
    origin = first_name === nothing ? nothing : _state_origin(flat, first_name)
    return diag(
        "E901",
        "the solver failed at t = $(t) (retcode = $(retcode))";
        hint = isempty(largest) ? "no states were available" : "largest states: " * largest,
        path = origin === nothing ? nothing : origin.path,
        block = origin === nothing ? nothing : origin.block,
        source = origin === nothing ? nothing : _origin_source(origin),
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

"""
    simulate(flat; run_dir, run_id, model_hash, settings, cancel, progress, phase,
             record_event) -> SimResult

Run the continuous model `flat` and write its run folder. See the file header for the run
loop and the plan sections it implements.

`record_event` is the J2.2 seam: when the discrete scheduler owns the run loop, it can pass
`record_event(t, side, values)` to receive each event instant twice (`side` is `:left` or
`:right`, both at the same `t`). The default is `nothing`, which writes both rows through the
recorder directly.
"""
function simulate(flat::Flat.FlatModel;
    run_dir::Union{AbstractString,Nothing} = nothing,
    run_id::Union{AbstractString,Nothing} = nothing,
    model_hash::Union{AbstractString,Nothing} = nothing,
    settings = RunSettings(),
    cancel = nothing,
    progress = nothing,
    phase = nothing,
    record_event = nothing,
)
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
    solver_problem = lowered.problem
    if haskey(lowered.problem.kwargs, :callback)
        limited = _with_event_limit(
            lowered.problem.kwargs[:callback], event_counter, run_settings.event_limit
        )
        solver_problem = remake(lowered.problem; callback = limited)
    end

    extra_states = length(lowered.model.int_states)
    states = Int(flat.stats.states) + extra_states
    equations = Int(flat.stats.equations) + extra_states

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
    _phase(phase, "init", 0.0)
    rec = open_recorder(
        dir, id, flat.name, hash, run_settings, flat.signals, flat_diagnostics;
        capacity = length(grid), states = states, equations = equations,
        created = running_manifest.created,
    )

    solver_kwargs = (; abstol = run_settings.abstol, reltol = run_settings.reltol)
    if run_settings.max_step !== nothing
        solver_kwargs = merge(solver_kwargs, (; dtmax = run_settings.max_step))
    end
    integ = try
        init(
            solver_problem, alg;
            solver_kwargs...,
            save_everystep = false,
            save_start = false,
            save_end = false,
        )
    catch err
        diagnostic = _initialization_diagnostic(err, flat)
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

    retcode = integ.sol.retcode
    if retcode == ReturnCode.InitialFailure
        diagnostic = diag(
            "E103", "initial conditions are inconsistent";
            hint = "the initialization returned $(retcode)", path = _last_path(flat),
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

    # One getter per recorded signal. Parameters (discrete values in J2) are read with
    # `getp`, everything else with `getu`; `getu` returns a callable whose argument is the
    # integrator (NOTES.md, section "Observed values with getu").
    symbols = Num[]
    for s in flat.signals
        x = get(lowered.model.vars, String(s.id), nothing)
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
    getters = [
        ModelingToolkit.isparameter(sym) ? getp(integ, sym) : getu(integ, sym) for
        sym in symbols
    ]
    values = () -> [Float64(getter(integ)) for getter in getters]

    # Row zero. `init` has run the initialization, so the state at t_start is valid.
    record_row!(rec, run_settings.t_start, values())
    flush_recorder!(rec)
    first_data_s = (time_ns() - start_ns) / 1.0e9
    _phase(phase, "simulate", 0.0)
    _progress(progress, run_settings.t_start, rec.nrows)

    status = "done"
    diagnostic = nothing
    loop_ns = time_ns()
    last_progress_ns = time_ns()
    last_flush_ns = time_ns()
    next_index = 2
    event_cursor = 0
    while next_index <= length(grid)
        if _cancelled(cancel)
            status = "cancelled"
            break
        end
        target = grid[next_index]
        tolerance = 1.0e-12 * max(1.0, abs(target))
        if integ.t >= target - tolerance
            record_row!(rec, target, values())
            next_index += 1
            now = time_ns()
            if now - last_progress_ns >= 100_000_000
                _progress(progress, target, rec.nrows)
                last_progress_ns = now
            end
            if now - last_flush_ns >= 100_000_000
                flush_recorder!(rec)
                last_flush_ns = now
            end
            continue
        end
        dt = target - integ.t
        if dt <= 0
            record_row!(rec, target, values())
            next_index += 1
            continue
        end
        before = integ.t
        step_ok = try
            step!(integ, dt, true)
            true
        catch err
            false
        end
        # Record every event instant that this step crossed, twice (left and right limits)
        # before the grid row for `target` is written.
        event_cursor = _record_new_events!(
            integ, rec, record_event, event_cursor, getters
        )
        if _event_limit_reached(event_counter, run_settings.event_limit)
            diagnostic = _event_limit_diagnostic(
                flat, integ.t, event_counter[], run_settings.event_limit
            )
            status = "done"
            break
        end
        if !step_ok || !_ok_retcode(integ.sol.retcode)
            diagnostic = _solver_diagnostic(integ, lowered.model, flat)
            status = "failed"
            break
        end
        if integ.t <= before && next_index <= length(grid)
            diagnostic = diag(
                "E901", "the solver made no progress at t = $(integ.t)";
                hint = "retcode = $(integ.sol.retcode)", path = _last_path(flat),
            )
            status = "failed"
            break
        end
        if _cancelled(cancel)
            status = "cancelled"
            break
        end
    end
    sim_s = (time_ns() - loop_ns) / 1.0e9

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
                  sort_diagnostics(vcat(flat_diagnostics, [diagnostic]))
    _phase(phase, "write", integ.t)
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
