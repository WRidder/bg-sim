# Parameter overrides and the parameter schedule of a run (plan/DASHBOARD_PLAN.md).
#
# `run.start` may carry
#
#   * `parameterOverrides`: `[{target, kind?, value}]`, a value for the whole run. An override
#     is applied to the *model document* before it is flattened (the node's `params[name]`
#     expression becomes the value), so everything the flattener derives from the parameter (a
#     start value `x(start = x0)`, another parameter's default, a constant fold) follows it,
#     exactly as if the user had typed the value into the block. A target that has no node in
#     the document (a parameter inside a composite library block) is applied to the flat model
#     instead ([`set_parameter_values`](@ref)). Parameter values are not part of the
#     structural key (D4), so an override never forces a recompile.
#   * `parameterSchedule`: `[{t, target, value}]`, a piecewise-constant change. A step at or
#     before `t_start` is a start override; a later step is a target of the run loop at its
#     exact time: the loop lands on `t` (`step!(integ, dt, true)`), records the left limit,
#     sets the parameter (`setp`, the same parameter discontinuity as a published discrete
#     output or a debug edit: the algebraic unknowns of a DAE are re-solved at the current
#     differential state) and records the right limit. Steps after `t_end` never apply.
#
# `kind` is `block` (the default: `target` is `<instance path>/<param>`) or `global` (`target`
# is `global:<name>`, a model-level global parameter). A global is folded to a number at
# compile time, so its override goes through `IR.override_globals` *before* static evaluation
# and flattening (every dependent global and instance expression is re-folded); it may change
# the structure and so the compile key. Globals cannot be scheduled.

"""    ParameterStepSpec(t, target, value)

One timed parameter change of a run (`parameterSchedule`)."""
struct ParameterStepSpec
    t::Float64
    target::String
    value::Float64
end

"""    ParameterInputs(overrides, schedule)

What a run was asked to change: `overrides` (`target => value`, in request order, a later
entry for the same target wins) and the `schedule`, sorted by time (stable)."""
struct ParameterInputs
    overrides::Vector{Pair{String,Any}}
    schedule::Vector{ParameterStepSpec}
end

ParameterInputs() = ParameterInputs(Pair{String,Any}[], ParameterStepSpec[])

Base.isempty(p::ParameterInputs) = isempty(p.overrides) && isempty(p.schedule)

const _TARGET_PATTERN = r"^(?:[A-Za-z_][A-Za-z0-9_]*/)+[A-Za-z_][A-Za-z0-9_]*$"
const _GLOBAL_TARGET_PATTERN = r"^global:[A-Za-z_][A-Za-z0-9_]*$"

_is_global_target(target::AbstractString) = startswith(target, IR.GLOBAL_OVERRIDE_PREFIX)

function _check_global_target(target, what::AbstractString)
    (target isa AbstractString && occursin(_GLOBAL_TARGET_PATTERN, target)) ||
        throw(ArgumentError("$what: a global target is written `global:<name>`, not `$target`"))
    return String(target)
end

_pfield(obj, key::String) = obj isa AbstractDict ?
    (haskey(obj, key) ? obj[key] : get(obj, Symbol(key), nothing)) : nothing

function _check_target(target, what::AbstractString)
    target isa AbstractString ||
        throw(ArgumentError("$what: `target` must be a string like `Motor1/R`"))
    occursin(_TARGET_PATTERN, target) || throw(ArgumentError(
        "$what: `$target` is not a block parameter; write `<instance path>/<parameter>`, " *
        "for example `Motor1/R`"
    ))
    return String(target)
end

function _check_number(value, what::AbstractString; bool_ok::Bool = false)
    bool_ok && value isa Bool && return value
    (value isa Real && !(value isa Bool) && isfinite(value)) ||
        throw(ArgumentError("$what: the value must be a finite number, not `$value`"))
    return Float64(value)
end

"""    parse_parameter_inputs(overrides, schedule) -> ParameterInputs

Validate the JSON `parameterOverrides` and `parameterSchedule` of a run request (either may be
`nothing`). Throws `ArgumentError` with a message naming the bad entry."""
function parse_parameter_inputs(overrides, schedule)
    out = Pair{String,Any}[]
    if overrides !== nothing
        overrides isa AbstractVector ||
            throw(ArgumentError("`parameterOverrides` must be an array"))
        for (i, o) in enumerate(overrides)
            what = "parameterOverrides[$i]"
            o isa AbstractDict || throw(ArgumentError("$what must be an object"))
            kind = _pfield(o, "kind")
            raw = _pfield(o, "target")
            if kind === nothing
                kind = raw isa AbstractString && _is_global_target(raw) ? "global" : "block"
            end
            if kind == "global"
                target = _check_global_target(raw, what)
                push!(out, target => _check_number(_pfield(o, "value"), what))
            elseif kind == "block"
                target = _check_target(raw, what)
                push!(out, target => _check_number(_pfield(o, "value"), what; bool_ok = true))
            else
                throw(ArgumentError(
                    "$what: target kind `$kind` is not supported (`block` or `global`)"
                ))
            end
        end
    end
    steps = ParameterStepSpec[]
    if schedule !== nothing
        schedule isa AbstractVector ||
            throw(ArgumentError("`parameterSchedule` must be an array"))
        for (i, s) in enumerate(schedule)
            what = "parameterSchedule[$i]"
            s isa AbstractDict || throw(ArgumentError("$what must be an object"))
            t = _check_number(_pfield(s, "t"), what * " t")
            raw = _pfield(s, "target")
            raw isa AbstractString && _is_global_target(raw) && throw(ArgumentError(
                "$what: `$raw` is a global parameter; globals are folded at compile time " *
                "and cannot change during a run (use a parameter override instead)"
            ))
            target = _check_target(raw, what)
            push!(steps, ParameterStepSpec(t, target, _check_number(_pfield(s, "value"), what)))
        end
        sort!(steps; by = s -> s.t, alg = Base.Sort.DEFAULT_STABLE)
    end
    return ParameterInputs(out, steps)
end

"""    start_inputs(inputs, t_start, t_end) -> (overrides, steps)

Split a run's inputs: the steps at or before `t_start` join the start overrides (after the
explicit overrides, so the schedule's first row wins), the steps in `(t_start, t_end]` stay
timed, later ones are dropped."""
function start_inputs(inputs::ParameterInputs, t_start::Real, t_end::Real)
    overrides = copy(inputs.overrides)
    steps = ParameterStepSpec[]
    tol = 1.0e-12 * max(1.0, abs(Float64(t_start)))
    for s in inputs.schedule
        if s.t <= t_start + tol
            push!(overrides, s.target => s.value)
        elseif s.t <= t_end + 1.0e-12 * max(1.0, abs(Float64(t_end)))
            push!(steps, s)
        end
    end
    return overrides, steps
end

# A parameter value as the constant expression a node's `params` holds.
function _override_expr(value)
    value isa Bool && return value ? "true" : "false"
    v = Float64(value)
    if isinteger(v) && abs(v) < 2.0^53
        return string(Int(v))
    end
    return repr(v)
end

function _find_node(diagram, names::AbstractVector{<:AbstractString})
    node = nothing
    current = diagram
    for (i, name) in enumerate(names)
        current === nothing && return nothing
        node = nothing
        for n in current.nodes
            n.name == name && (node = n; break)
        end
        node === nothing && return nothing
        i < length(names) || break
        current = node.block_kind === :subsystem ? node.subsystem : nothing
    end
    return node
end

"""    apply_parameter_overrides!(md::IR.ModelDoc, overrides) -> Vector{Pair{String,Any}}

Write each override into its node's `params` (a fresh parse of the document is mutated).
Returns the overrides that have no node in the document (a parameter of an instance inside a
composite library block); the caller applies those to the flat model."""
function apply_parameter_overrides!(md::IR.ModelDoc, overrides)
    rest = Pair{String,Any}[]
    for (target, value) in overrides
        parts = split(target, '/')
        node = _find_node(md.diagram, parts[1:end-1])
        if node === nothing || node.block_kind === :junction || node.block_kind === :subsystem
            push!(rest, target => value)
            continue
        end
        node.params[String(parts[end])] = _override_expr(value)
    end
    return rest
end

"""    flatten_with_overrides(md, overrides; project_dir) -> FlatModel

Flatten `md` with `overrides` applied (see the file header). Throws `ArgumentError` for a
target that is not a parameter of the flattened model."""
function flatten_with_overrides(md::IR.ModelDoc, overrides; project_dir = nothing)
    globals = Dict{String,Any}(t => v for (t, v) in overrides if _is_global_target(t))
    blocks = Pair{String,Any}[t => v for (t, v) in overrides if !_is_global_target(t)]
    # Globals first, before static evaluation (an unknown global throws ArgumentError).
    md = IR.override_globals(md, globals)
    rest = apply_parameter_overrides!(md, blocks)
    flat = Compile.flatten(md; project_dir = project_dir)
    any(d -> d.severity == "error", flat.diagnostics) && return flat
    known = Dict(p.id => p for p in flat.parameters)
    for (target, _) in blocks
        p = get(known, target, nothing)
        p === nothing && throw(ArgumentError(_unknown_parameter_message(flat, target)))
    end
    if !isempty(rest)
        updates = Dict{String,Any}()
        for (target, value) in rest
            updates[target] = value isa Bool ? value : Float64(value)
        end
        flat = set_parameter_values(flat, updates)
    end
    return flat
end

function _unknown_parameter_message(flat, target::AbstractString)
    near = _near_ids((p.id for p in flat.parameters), target)
    hint = isempty(near) ? "" : " Did you mean " * join(("`$n`" for n in near), ", ") * "?"
    return "`$target` is not a parameter of `$(flat.name)`.$hint"
end

"""    check_schedule_targets(flat, steps)

Refuse a schedule step whose target is not a runtime parameter of `flat` (an unknown name or
a held discrete output). Throws `ArgumentError`."""
function check_schedule_targets(flat, steps)
    known = Dict(p.id => p for p in flat.parameters)
    for s in steps
        p = get(known, s.target, nothing)
        p === nothing && throw(ArgumentError(_unknown_parameter_message(flat, s.target)))
        get(p.attrs, :kind, nothing) === :discrete && throw(ArgumentError(
            "`$(s.target)` is a held discrete output, not a parameter a schedule can set"
        ))
    end
    return nothing
end

"""    parameter_inputs_manifest(inputs) -> NamedTuple

The `parameterOverrides` / `parameterSchedule` manifest fields of a run (empty ones omitted)."""
function parameter_inputs_manifest(inputs::ParameterInputs)
    fields = Pair{Symbol,Any}[]
    if !isempty(inputs.overrides)
        push!(fields, :parameterOverrides => [
            _is_global_target(t) ? (target = t, kind = "global", value = v) :
                (target = t, value = v)
            for (t, v) in inputs.overrides
        ])
    end
    if !isempty(inputs.schedule)
        push!(fields, :parameterSchedule => [
            (t = s.t, target = s.target, value = s.value) for s in inputs.schedule
        ])
    end
    return (; fields...)
end

# ---------------------------------------------------------------------------------------
# The run loop side
# ---------------------------------------------------------------------------------------

# A resolved timed step: the MTK parameter and its setter on the live integrator.
struct _LiveStep
    t::Float64
    target::String
    setter::Any
    value::Float64
end

function _resolve_steps(steps::Vector{ParameterStepSpec}, model, integ)
    out = _LiveStep[]
    for s in steps
        sym = get(model.params, s.target, nothing)
        sym === nothing && throw(ArgumentError(
            "`$(s.target)` has no runtime parameter in the compiled model"
        ))
        push!(out, _LiveStep(s.t, s.target, setp(integ, sym), s.value))
    end
    return out
end

"""    schedule_targets(targets, steps) -> Vector{RunTarget}

Add a loop target (neither grid nor tick) at every step time that is not already a target."""
function schedule_targets(targets::Vector{RunTarget}, steps)
    isempty(steps) && return targets
    out = copy(targets)
    for s in steps
        tol = 1.0e-12 * max(1.0, abs(s.t))
        any(r -> abs(r.t - s.t) <= tol, out) && continue
        push!(out, RunTarget(s.t, false, false, 0))
    end
    sort!(out; by = r -> r.t, alg = Base.Sort.DEFAULT_STABLE)
    return out
end

# Apply every step due at `tt` (index `next` on); returns the next index. The parameter
# discontinuity is handled like a published held output in `run_tick!`.
function _apply_due_steps!(steps::Vector{_LiveStep}, next::Int, tt::Float64, integ,
    algebraic::Bool)
    tol = 1.0e-12 * max(1.0, abs(tt))
    applied = false
    while next <= length(steps) && steps[next].t <= tt + tol
        s = steps[next]
        s.setter(integ, s.value)
        applied = true
        next += 1
    end
    if applied
        algebraic && reinit_algebraic!(integ)
        ModelingToolkit.SciMLBase.reeval_internals_due_to_modification!(
            integ, false; callback_initializealg = ModelingToolkit.SciMLBase.NoInit()
        )
    end
    return next
end

_steps_due(steps::Vector{_LiveStep}, next::Int, tt::Float64) =
    next <= length(steps) && steps[next].t <= tt + 1.0e-12 * max(1.0, abs(tt))

export ParameterInputs, ParameterStepSpec, parse_parameter_inputs, flatten_with_overrides
