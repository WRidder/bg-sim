# Edits, replay and branch (plan 5.13 "Edits, replay and branch", decisions D24 and D25; work
# package J4.4).
#
#   * `debug_set_parameter!` / `debug_set_state!` change the live integrator of a paused debug
#     run and append an `Edit` `(t, kind, target, value)` to `ctx.edits`, which the manifest
#     stores in `debug.edits`. A parameter is always editable (D4: every parameter is a runtime
#     value); a state only when it is a differential state of the compiled system and no
#     algebraic equation depends on a differential state (otherwise E402, D24). Held discrete
#     outputs are read-only.
#   * A *replay* (`replay_run`) re-runs the model from the parent's manifest and applies every
#     edit at the place of the loop where it was made; a *branch* (`branch_run`) replays the
#     edits made before `t`, pauses at `t` and records `parentRun` and `branchAt` (D25).
#     Runs are deterministic, so a re-run is an exact rewind.
#
# Where an edit sits in the loop. The debug loop has three checkpoints (src/sim/debug.jl):
# `:entry` (after row zero), `:step` (after every internal integrator step) and `:target`
# (after a tick/grid target's partitions and row). An edit made at a pause is the same
# operation on the same state whichever way it is made, so a replay is bit-identical when it
# applies the edit at the same checkpoint. The checkpoint is stored in the edit's
# `$comment` (`at=entry|step|target|statement`; the contract keeps `$comment` free for this),
# because the contract's `Edit` has no field for it. A statement pause is replayed as a `:step`
# edit at its tick time: the edit then takes effect before the tick instead of in the middle of
# it, which is the same operation unless a later partition of the same tick reads the edited
# parameter (NOTES.md, J4.4).
#
# A replay is a debug run (`DebugCtx` with a [`ReplayPlan`](@ref)) that never pauses. A debug
# run without pauses writes the same bytes as a normal run (J4.1), so the replay is the normal
# run plus the edits and the extra time stops of the parent.

import JSON3
import SymbolicIndexingInterface

# ---------------------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------------------

_edit_diag(code, message; hint = nothing) =
    to_namedtuple(diag(code, message; hint = hint, scope = "edit"))

function _near_ids(ids, name::AbstractString; limit::Int = 4)
    base = last(split(name, "/"))
    near = String[]
    for other in sort!(collect(String, ids))
        (other == name || endswith(other, "/" * base) || occursin(name, other)) || continue
        length(near) < limit && push!(near, other)
    end
    return near
end

function _differential_names(sys)
    out = Set{String}()
    for eq in ModelingToolkit.equations(sys)
        Compile._collect_differentials!(out, eq.lhs)
        Compile._collect_differentials!(out, eq.rhs)
    end
    return out
end

function _expr_names(expr)
    names = Set{String}()
    for v in Symbolics.get_variables(expr)
        ModelingToolkit.isvariable(v) && push!(names, signal_name(Symbolics.wrap(v)))
    end
    return names
end

# The algebraic equations of the compiled system (no derivative on the left) whose solution
# depends on a differential state, directly or through the observed equations. A state edit
# would leave such an equation inconsistent, and re-initializing a DAE is not attempted (D24).
function _coupled_algebraic_equations(model::CompiledModel, differential::Set{String})
    sys = model.system
    algebraic = Any[]
    for eq in ModelingToolkit.equations(sys)
        lhs_diff = Set{String}()
        Compile._collect_differentials!(lhs_diff, eq.lhs)
        isempty(lhs_diff) && push!(algebraic, eq)
    end
    isempty(algebraic) && return (0, 0)
    observed = Dict{String,Any}()
    for eq in ModelingToolkit.observed(sys)
        lhs = Symbolics.unwrap(eq.lhs)
        ModelingToolkit.isvariable(lhs) || continue
        observed[signal_name(Symbolics.wrap(lhs))] = eq.rhs
    end
    coupled = 0
    for eq in algebraic
        seen = Set{String}()
        todo = collect(_expr_names(eq.rhs - eq.lhs))
        hit = false
        while !isempty(todo) && !hit
            name = pop!(todo)
            name in seen && continue
            push!(seen, name)
            if name in differential
                hit = true
            elseif haskey(observed, name)
                append!(todo, _expr_names(observed[name]))
            end
        end
        hit && (coupled += 1)
    end
    return (length(algebraic), coupled)
end

_symbolic_zero(x) = (y = Symbolics.simplify(x); y isa Number ? iszero(y) : isequal(y, 0))

# True when every algebraic equation (observed equations substituted) is linear in the
# algebraic unknowns. Then the algebraic unknowns are the unique, exactly solvable function of
# the differential states, and one Newton step of the Brown initialization restores
# consistency after a state edit. A nonlinear loop has no such guarantee (E402).
function _algebraic_linear(model::CompiledModel, differential::Set{String})
    sys = model.system
    rules = Dict{Any,Any}()
    for eq in ModelingToolkit.observed(sys)
        rules[Symbolics.unwrap(eq.lhs)] = Symbolics.unwrap(eq.rhs)
    end
    algvars = Any[
        Symbolics.unwrap(u) for u in ModelingToolkit.unknowns(sys) if
        !(signal_name(Symbolics.wrap(u)) in differential)
    ]
    for eq in ModelingToolkit.equations(sys)
        lhs_diff = Set{String}()
        Compile._collect_differentials!(lhs_diff, eq.lhs)
        isempty(lhs_diff) || continue
        r = Symbolics.unwrap(eq.rhs - eq.lhs)
        for _ in 1:50
            next = Symbolics.substitute(r, rules)
            isequal(next, r) && break
            r = next
        end
        for a in algvars
            da = Symbolics.derivative(r, a)
            for b in algvars
                _symbolic_zero(Symbolics.derivative(da, b)) || return false
            end
        end
    end
    return true
end

# ---------------------------------------------------------------------------------------
# Edit records
# ---------------------------------------------------------------------------------------

# The Edit of plan 3.8 with the checkpoint in `$comment`.
function _edit_record(t::Real, kind::AbstractString, target::AbstractString, value::Real,
    at::AbstractString)
    return (
        t = Float64(t), kind = String(kind), target = String(target), value = Float64(value),
        var"$comment" = "at=" * at,
    )
end

# The checkpoint of the current pause, as stored in the edit.
function _pause_position(s::DebugSession)
    ctx = s.ctx
    s.info !== nothing && s.info.reason == "exception" && throw(DebugStateError(
        "the run is paused at a failure and ends here; edits are not allowed"
    ))
    haskey(ctx.ext, :frame) && return "statement"
    ctx.at === :entry && return "entry"
    ctx.at === :target && return "target"
    return "step"
end

# ---------------------------------------------------------------------------------------
# Validation and the operations
# ---------------------------------------------------------------------------------------

function _finite_value(value, what)
    value isa Real && !(value isa Bool) && isfinite(value) && return nothing
    return _edit_diag(
        "E004", "the new value of `$what` must be a finite number, not `$value`";
        hint = "give a finite real number",
    )
end

# Returns `(symbol, diagnostics)`.
function _check_parameter(s::DebugSession, name::AbstractString, value)
    model = s.lowered
    bad = _finite_value(value, name)
    bad === nothing || return (nothing, Any[bad])
    entry = nothing
    for p in s.flat.parameters
        p.id == name && (entry = p; break)
    end
    if entry !== nothing && get(entry.attrs, :kind, nothing) === :discrete
        return (nothing, Any[_edit_diag(
            "E402", "`$name` is a held discrete output and is read-only while paused";
            hint = "change a parameter that the discrete block reads, or start a new run with " *
                   "a different value in the block",
        )])
    end
    sym = get(model.params, String(name), nothing)
    if sym === nothing || entry === nothing
        near = _near_ids(keys(model.params), name)
        hint = if haskey(model.vars, String(name))
            "`$name` is a signal, not a parameter; change a differential state with " *
            "debug.setState, or change a parameter it depends on"
        elseif isempty(near)
            "list the parameters with the signal browser; structural constants (`constants`) " *
            "are compiled in and need a new run"
        else
            "did you mean " * join(("`$n`" for n in near), ", ") *
            "? Structural constants (`constants`) are compiled in and need a new run"
        end
        return (nothing, Any[_edit_diag(
            "E003", "`$name` is not a parameter of this model"; hint = hint,
        )])
    end
    return (sym, Any[])
end

# Returns `(symbol, diagnostics)`.
function _check_state(s::DebugSession, id::AbstractString, value)
    model = s.lowered
    bad = _finite_value(value, id)
    bad === nothing || return (nothing, Any[bad])
    if !haskey(model.vars, String(id)) && !haskey(model.params, String(id))
        near = _near_ids(keys(model.vars), id)
        return (nothing, Any[_edit_diag(
            "E003", "`$id` is not a signal of this model";
            hint = isempty(near) ? "list the states with model.explain or the signal browser" :
                   "did you mean " * join(("`$n`" for n in near), ", ") * "?",
        )])
    end
    explained = explain_signal(s.flat, model, id)
    differential = _differential_names(model.system)
    var = haskey(model.vars, String(id)) ? Symbolics.unwrap(model.vars[String(id)]) : nothing
    is_state = var !== nothing && explained.kind == "state" &&
               any(u -> isequal(Symbolics.unwrap(u), var), ModelingToolkit.unknowns(model.system))
    states = sort!(collect(String, filter(n -> haskey(model.vars, n), differential)))
    listing = isempty(states) ? "" :
              " Differential states of this model: " * join(first(states, 6), ", ") *
              (length(states) > 6 ? ", ..." : "") * "."
    if !is_state
        reason = explained.kind == "alias" && explained.aliasOf !== nothing ?
                 "an alias of `$(explained.aliasOf)`" :
                 explained.kind in ("parameter", "discrete") ? "a parameter or held output" :
                 "$(explained.kind == "algebraic" ? "an algebraic unknown" : "an observed signal")"
        return (nothing, Any[_edit_diag(
            "E402", "`$id` is not a differential state ($reason), so it cannot be changed";
            hint = "change a parameter instead, edit the differential state it is computed " *
                   "from, or start a new run with a different start value." * listing,
        )])
    end
    algebraic, coupled = _coupled_algebraic_equations(model, differential)
    if coupled > 0 && !_algebraic_linear(model, differential)
        return (nothing, Any[_edit_diag(
            "E402", "`$id` cannot be changed: the compiled system keeps $algebraic " *
                    "algebraic equation(s), $coupled of them nonlinear and dependent on a " *
                    "differential state, which would need a consistent re-initialization";
            hint = "change a parameter instead, or start a new run with a different start " *
                   "value for `$id`",
        )])
    end
    return (model.vars[String(id)], Any[])
end

# A parameter changes discontinuously at the current time: the same treatment as a published
# held output (`run_tick!`): neither `u` nor `t` changes, the algebraic unknowns of a DAE are
# made consistent with the new value at the current differential state (Brown full basic
# init; the problem's own initialization would jump back to the t = 0 operating point), and
# the derivative data is marked stale.
function _apply_parameter!(s::DebugSession, sym, value::Float64)
    integ = s.integ
    setp(integ, sym)(integ, value)
    if s.lowered.algebraic
        ModelingToolkit.SciMLBase.initialize_dae!(
            integ, OrdinaryDiffEqNonlinearSolve.BrownFullBasicInit()
        )
    end
    ModelingToolkit.SciMLBase.reeval_internals_due_to_modification!(
        integ, false; callback_initializealg = ModelingToolkit.SciMLBase.NoInit()
    )
    return nothing
end

# A state is written in place. On a DAE the algebraic equations are linear in the algebraic
# unknowns (checked in `_check_state`), so the Brown initialization (differential states held
# fixed) restores consistency exactly; the derivative data is then marked stale. The
# interpolation of the finished step is not used again.
function _apply_state!(s::DebugSession, sym, value::Float64)
    integ = s.integ
    SymbolicIndexingInterface.setu(integ, sym)(integ, value)
    if s.lowered.algebraic
        ModelingToolkit.SciMLBase.initialize_dae!(
            integ, OrdinaryDiffEqNonlinearSolve.BrownFullBasicInit()
        )
    end
    ModelingToolkit.SciMLBase.reeval_internals_due_to_modification!(
        integ, false; callback_initializealg = ModelingToolkit.SciMLBase.NoInit()
    )
    return nothing
end

function _record_edit!(s::DebugSession, edit)
    push!(s.ctx.edits, edit)
    dbg_sync_manifest!(s)
    return edit
end

"""
    debug_set_parameter!(ctx, name, value) -> (; ok, edit, diagnostics)

Change the parameter `name` (its signal id, for example `Motor1/R`) of the paused run to
`value` and append the `Edit` to `ctx.edits` and the manifest's `debug.edits` (D24, D25). The
change is the same parameter discontinuity as a published held output, so it works on an ODE
and a DAE. An unknown name, a structural constant, a held discrete output or a non-finite value
gives a diagnostic with a hint, `ok = false` and no edit. Throws `DebugStateError` when the run
is not paused."""
function debug_set_parameter!(ctx::DebugCtx, name::AbstractString, value)
    return with_paused(ctx) do s
        position = _pause_position(s)
        sym, diagnostics = _check_parameter(s, name, value)
        sym === nothing && return (ok = false, edit = nothing, diagnostics = diagnostics)
        _apply_parameter!(s, sym, Float64(value))
        edit = _record_edit!(
            s, _edit_record(s.integ.t, "parameter", name, value, position)
        )
        return (ok = true, edit = edit, diagnostics = Any[])
    end
end

"""
    debug_set_state!(ctx, id, value) -> (; ok, edit, diagnostics)

Change the differential state `id` of the paused run to `value` (D24). Refused with **E402**
(`ok = false`, no edit) when `id` is not a differential state of the compiled system, or when
the system keeps an algebraic equation that depends on a differential state: changing a DAE
state would need a consistent re-initialization, which is not attempted. Throws
`DebugStateError` when the run is not paused."""
function debug_set_state!(ctx::DebugCtx, id::AbstractString, value)
    return with_paused(ctx) do s
        position = _pause_position(s)
        sym, diagnostics = _check_state(s, id, value)
        sym === nothing && return (ok = false, edit = nothing, diagnostics = diagnostics)
        _apply_state!(s, sym, Float64(value))
        edit = _record_edit!(s, _edit_record(s.integ.t, "state", id, value, position))
        return (ok = true, edit = edit, diagnostics = Any[])
    end
end

# ---------------------------------------------------------------------------------------
# The parent run
# ---------------------------------------------------------------------------------------

"""
    ReplayEdit

One edit of a parent run: `t`, `kind` (`"parameter"` or `"state"`), `target`, `value`, `at`
(the replay checkpoint `:entry`, `:step` or `:target`) and `comment`, the stored `\$comment`."""
struct ReplayEdit
    t::Float64
    kind::String
    target::String
    value::Float64
    at::Symbol
    comment::String
end

"""
    ParentRun

The parts of a finished or paused debug run that a replay or branch needs, read from its run
folder: the run id, model hash, settings, `debug.edits` and `debug.pauses`."""
struct ParentRun
    dir::String
    id::String
    model_hash::String
    settings::RunSettings
    edits::Vector{ReplayEdit}
    pauses::Vector{NamedTuple{(:t, :reason),Tuple{Float64,String}}}
end

const _COMMENT_KEY = Symbol("\$comment")

function _edit_checkpoint(comment)
    comment isa AbstractString || return :step
    occursin("at=entry", comment) && return :entry
    occursin("at=target", comment) && return :target
    return :step     # "at=step" and "at=statement"
end

function _parse_replay_edit(e)
    raw = _plain(e)
    kind = String(raw["kind"])
    kind in ("parameter", "state") || throw(ArgumentError("unknown edit kind `$kind`"))
    comment = String(get(raw, "\$comment", "at=step"))
    return ReplayEdit(
        Float64(raw["t"]), kind, String(raw["target"]), Float64(raw["value"]),
        _edit_checkpoint(comment), comment,
    )
end

"""    load_parent_run(run_dir_or_manifest) -> ParentRun"""
function load_parent_run(path::AbstractString)
    file = isdir(path) ? joinpath(path, "manifest.json") : String(path)
    isfile(file) || throw(ArgumentError("no run manifest at `$file`"))
    m = JSON3.read(read(file, String))
    debug = get(m, :debug, nothing)
    edits = ReplayEdit[]
    pauses = NamedTuple{(:t, :reason),Tuple{Float64,String}}[]
    if debug !== nothing
        for e in get(debug, :edits, ())
            push!(edits, _parse_replay_edit(e))
        end
        for p in get(debug, :pauses, ())
            push!(pauses, (t = Float64(p.t), reason = String(p.reason)))
        end
    end
    return ParentRun(
        dirname(file), String(m.id), String(m.modelHash), RunSettings(m.settings), edits,
        pauses,
    )
end

# ---------------------------------------------------------------------------------------
# The model document of a run
# ---------------------------------------------------------------------------------------

"""
    write_run_model(run_dir, model, project_dir)

Persist the model document a run was started from as `<run_dir>/model.json`
(`{ "projectDir": ..., "model": ... }`), so `run.replay` and `run.branch` can rebuild the
parent after the worker forgot it. `model` is a `Dict`, a JSON3 object, JSON text or a path."""
function write_run_model(run_dir::AbstractString, model, project_dir)
    doc = if model isa AbstractString
        text = isfile(model) ? read(model, String) : String(model)
        JSON3.read(text)
    else
        model
    end
    mkpath(run_dir)
    open(joinpath(run_dir, "model.json"), "w") do io
        JSON3.write(io, (projectDir = project_dir === nothing ? nothing : String(project_dir),
            model = doc))
        write(io, '\n')
    end
    return nothing
end

"""    load_run_flat(run_dir) -> Flat.FlatModel

Flatten the model that `write_run_model` stored in `run_dir`."""
function load_run_flat(run_dir::AbstractString)
    file = joinpath(run_dir, "model.json")
    isfile(file) || throw(ArgumentError(
        "no model.json in `$run_dir`: the run's model document was not saved (pass `flat`)"
    ))
    stored = JSON3.read(read(file, String), Dict{String,Any})
    project_dir = get(stored, "projectDir", nothing)
    return Compile.flatten(
        IR.parse_model(stored["model"]);
        project_dir = project_dir === nothing ? nothing : String(project_dir),
    )
end

# ---------------------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------------------

"""
    ReplayPlan

What a replay or branch run applies: the parent's `edits` (at their checkpoints) and the time
`stops` the parent's session added (pauses with reason `time` or `breakpoint`: a time
breakpoint, `runTo` or a located watch crossing), as `add_tstop!` before the first step. Held
in `ctx.replay`; `next` counts the applied edits."""
mutable struct ReplayPlan
    parent_run::String
    branch_at::Union{Nothing,Float64}
    edits::Vector{ReplayEdit}
    stops::Vector{Float64}
    next::Int
    started::Bool
end

_edit_tolerance(t) = 1.0e-12 * max(1.0, abs(t))

# An edit that was made at a pause of a run whose time stops are replayed. A refused replay
# edit means the model is not the parent's; it ends the run with an error.
function _replay_apply!(s::DebugSession, e::ReplayEdit)
    sym, diagnostics = e.kind == "parameter" ? _check_parameter(s, e.target, e.value) :
                       _check_state(s, e.target, e.value)
    if sym === nothing
        d = first(diagnostics)
        error("replay: the edit of `$(e.target)` at t = $(e.t) is refused ($(d.code): $(d.message))")
    end
    e.kind == "parameter" ? _apply_parameter!(s, sym, e.value) : _apply_state!(s, sym, e.value)
    push!(s.ctx.edits, (
        t = e.t, kind = e.kind, target = e.target, value = e.value,
        var"$comment" = e.comment,
    ))
    return nothing
end

# The replay's checkpoint, called by the debug loop at `:entry`, `:step` and `:target`.
function _replay_checkpoint!(s::DebugSession, pos::Symbol)
    plan = s.ctx.replay::ReplayPlan
    if !plan.started
        plan.started = true
        for t in plan.stops
            s.integ.t < t <= s.settings.t_end && ModelingToolkit.SciMLBase.add_tstop!(s.integ, t)
        end
        info = plan.branch_at === nothing ? (parentRun = plan.parent_run,) :
               (parentRun = plan.parent_run, branchAt = plan.branch_at)
        s.rec.manifest = merge(s.rec.manifest, info)
        _write_debug_manifest!(s, "running")
    end
    while plan.next <= length(plan.edits)
        e = plan.edits[plan.next]
        e.at === pos || break
        pos === :entry || s.integ.t >= e.t - _edit_tolerance(e.t) || break
        if pos === :step
            # A pause records the event instants of the last step first (`dbg_pause!`); the
            # edit must see the same rows as the interactive session.
            s.event_cursor = _record_new_events!(
                s.integ, s.rec, s.record_event, s.event_cursor, s.getters
            )
        end
        _replay_apply!(s, e)
        plan.next += 1
    end
    return nothing
end

_replay_stop(p) = p.reason in ("time", "breakpoint")

"""
    prepare_replay!(ctx, parent; branch_at = nothing) -> ctx

Arm the fresh `ctx` to replay `parent` (a [`ParentRun`](@ref)). With `branch_at = t` only the
edits made before `t` and the time stops before `t` are replayed, and a one-shot time
breakpoint pauses the run at `t` with reason `time`. The context's `pauses` start with the
replayed stops, so a replay of this run's manifest reproduces it. Call it before `simulate`."""
function prepare_replay!(ctx::DebugCtx, parent::ParentRun; branch_at = nothing)
    ctx.state[] == _STATE_NEW || throw(ArgumentError("a replay needs a fresh DebugCtx"))
    ctx.replay === nothing || throw(ArgumentError("the DebugCtx already has a replay plan"))
    if branch_at !== nothing
        t = Float64(branch_at)
        s = parent.settings
        s.t_start < t <= s.t_end || throw(ArgumentError(
            "a branch time must lie in ($(s.t_start), $(s.t_end)], not $t"
        ))
        branch_at = t
    end
    before(t) = branch_at === nothing || t < branch_at
    edits = ReplayEdit[e for e in parent.edits if before(e.t)]
    pauses = [p for p in parent.pauses if before(p.t)]
    stops = unique(Float64[p.t for p in pauses if _replay_stop(p)])
    ctx.replay = ReplayPlan(parent.id, branch_at, edits, stops, 1, false)
    append!(ctx.pauses, pauses)
    if branch_at !== nothing
        bps = Any[bp.raw for bp in ctx.breakpoints]
        push!(bps, Dict{String,Any}(
            "id" => "branch", "enabled" => true, "kind" => "time",
            "time" => Dict{String,Any}("t" => branch_at),
        ))
        debug_set_breakpoints!(ctx, bps)
    end
    return ctx
end

function _check_replayed(ctx::DebugCtx, result)
    plan = ctx.replay::ReplayPlan
    if result.status == "done" && plan.next <= length(plan.edits)
        e = plan.edits[plan.next]
        error(
            "replay: the run ended before $(length(plan.edits) - plan.next + 1) edit(s) were " *
            "applied (next: `$(e.target)` at t = $(e.t)); the model is not the parent's"
        )
    end
    return result
end

function _run_replay(parent::ParentRun, ctx::DebugCtx, flat; run_dir, run_id, settings,
    model_hash, kwargs...)
    flat === nothing && (flat = load_run_flat(parent.dir))
    result = simulate(
        flat; run_dir = run_dir, run_id = run_id,
        model_hash = model_hash === nothing ? parent.model_hash : model_hash,
        settings = settings === nothing ? parent.settings : settings,
        debug = ctx, kwargs...,
    )
    return _check_replayed(ctx, result)
end

"""
    replay_run(parent_run_dir; run_dir, run_id, flat = nothing, settings = nothing,
               model_hash = nothing, cancel, progress, phase, record_event) -> SimResult

`run.replay`: run the parent's model again as a run that never pauses and applies the parent's
`debug.edits` at the places they were made (D25). The result's `columns.f64` equals the
parent's bit for bit when the edits were made at tick, statement, step, time or pause-request
pauses, and within the solver tolerances for a watch pause. The new manifest has `parentRun`
(the parent's id) and the applied edits and pauses in `debug.edits` / `debug.pauses`.

`parent_run_dir` is the parent's run folder (or its `manifest.json`); the model is `flat`, or
the document `write_run_model` stored there. The parent's settings and model hash are used
unless given."""
function replay_run(parent_run_dir::AbstractString; run_dir, run_id, flat = nothing,
    settings = nothing, model_hash = nothing, kwargs...)
    parent = load_parent_run(parent_run_dir)
    ctx = prepare_replay!(DebugCtx(), parent)
    return _run_replay(parent, ctx, flat; run_dir, run_id, settings, model_hash, kwargs...)
end

"""
    branch_run(parent_run_dir, t; ctx = DebugCtx(), run_dir, run_id, flat = nothing, ...) -> SimResult

`run.branch` (D25): a debug run that replays the parent's edits and time stops before `t`,
pauses at `t` with reason `time`, and then continues as an ordinary debug session driven
through `ctx` (continue, step, edits). The rows before `t` equal the parent's bit for bit. The
manifest has `parentRun` and `branchAt`. Blocks until the run ends, so call it on the run task
(`ctx` carries `on_paused`). `t` must lie in `(t_start, t_end]`."""
function branch_run(parent_run_dir::AbstractString, t::Real; ctx::DebugCtx = DebugCtx(),
    run_dir, run_id, flat = nothing, settings = nothing, model_hash = nothing, kwargs...)
    parent = load_parent_run(parent_run_dir)
    prepare_replay!(ctx, parent; branch_at = t)
    return _run_replay(parent, ctx, flat; run_dir, run_id, settings, model_hash, kwargs...)
end

export debug_set_parameter!, debug_set_state!
export ParentRun, ReplayEdit, ReplayPlan, load_parent_run, prepare_replay!
export replay_run, branch_run, write_run_model, load_run_flat
