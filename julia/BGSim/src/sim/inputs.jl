# Driving parameters from a sampled trajectory during a run (plan/EXPORT_PLAN.md X-EX1).
#
# `simulate(flat; inputs = Dict(id => (t, u)))` holds the parameter `id` piecewise constant:
# it takes `u[k]` on `[t[k], t[k+1])` and keeps `u[end]` after `t[end]`; before `t[1]` it has
# its model value. This is the zero-order hold of a co-simulation host, and the run reproduces
# an FMU's view of its inputs exactly:
#
#   * a change at `t[k]` is applied when the run reaches `t[k]` (an exact stop of the
#     integrator), *after* a discrete tick at the same instant. So a tick at `t[k]` samples
#     the value held over `[t[k-1], t[k])`, as the FMU's tick at the end of its `doStep` does
#     before the host sets the next input;
#   * the change is a parameter discontinuity, applied as a held discrete output is
#     (`run_tick!`): `setp`, the algebraic unknowns of a DAE re-solved at the current state,
#     the integrator's derivative data refreshed. Neither `u` nor `t` jumps;
#   * a change that alters the value records the left and the right limit at the instant
#     (one pair with a tick at the same instant), so a grid row shows the value after it;
#   * a change at or before `t_start` is applied before row zero (after `init`, which keeps
#     the start state of the model value, like an FMU's baked start).
#
# The export marker inputs are parameters `<marker>/value` (`Export.input_markers`); a
# pass-through marker is driven on `Export.host_inputs(flat)`.

"""One driven parameter: its id, the change instants and the held values."""
struct DrivenInput
    id::String
    t::Vector{Float64}
    u::Vector{Float64}
end

function _input_series(id, data)
    t, u = if data isa Tuple && length(data) == 2
        data
    elseif data isa NamedTuple
        (data.t, data.u)
    elseif data isa AbstractDict
        (get(data, "t", get(data, :t, nothing)), get(data, "u", get(data, :u, nothing)))
    else
        throw(ArgumentError("input `$id`: expected (t, u), (t = ..., u = ...) or Dict(\"t\" => ..., \"u\" => ...)"))
    end
    (t === nothing || u === nothing) && throw(ArgumentError("input `$id` needs both `t` and `u`"))
    t = Float64.(collect(t))
    u = Float64.(collect(u))
    length(t) == length(u) || throw(ArgumentError("input `$id`: `t` and `u` differ in length"))
    isempty(t) && throw(ArgumentError("input `$id` has no samples"))
    all(isfinite, t) && all(isfinite, u) || throw(ArgumentError("input `$id` has a non-finite sample"))
    all(>(0), diff(t)) || throw(ArgumentError("input `$id`: `t` must be strictly increasing"))
    return DrivenInput(String(id), t, u)
end

"""    driven_inputs(flat, inputs) -> Vector{DrivenInput}

Check `inputs` (id => trajectory) against the model: every id is a parameter of `flat` that
is not a held discrete value."""
function driven_inputs(flat::Flat.FlatModel, inputs)
    inputs === nothing && return DrivenInput[]
    params = Dict(p.id => p for p in flat.parameters)
    out = DrivenInput[]
    for (k, data) in pairs(inputs)
        id = String(k)
        p = get(params, id, nothing)
        p === nothing && throw(ArgumentError("input `$id` is not a parameter of `$(flat.name)`" *
            " (an export marker's input is `<marker>/value`)"))
        get(p.attrs, :kind, nothing) === :discrete &&
            throw(ArgumentError("input `$id` is a held discrete value, which only its partition writes"))
        push!(out, _input_series(id, data))
    end
    return out
end

"""The run-loop state of the driven inputs: one `setp` per input and a cursor per input."""
mutable struct InputDrive
    inputs::Vector{DrivenInput}
    setters::Vector{Any}
    getters::Vector{Any}
    next::Vector{Int}          # the next sample index of each input not applied yet
    dae::Bool
end

function InputDrive(inputs::Vector{DrivenInput}, model, integ)
    setters = Any[setp(integ, model.params[d.id]) for d in inputs]
    getters = Any[getp(integ, model.params[d.id]) for d in inputs]
    return InputDrive(inputs, setters, getters, ones(Int, length(inputs)), model.algebraic)
end

"""Every change instant after `t_start` (sorted, unique), to merge into the run targets."""
function input_times(drive::InputDrive, t_start, t_end)
    ts = Float64[]
    for d in drive.inputs, tk in d.t
        tol = 1.0e-12 * max(1.0, abs(tk))
        tk > t_start + tol && tk <= t_end + tol && push!(ts, tk)
    end
    return sort!(unique!(ts))
end

"""Whether a sample of any input is due at `t` (within 1e-12 relative)."""
function inputs_due(drive::InputDrive, t::Float64)
    tol = 1.0e-12 * max(1.0, abs(t))
    for (j, d) in enumerate(drive.inputs)
        k = drive.next[j]
        k <= length(d.t) && d.t[k] <= t + tol && return true
    end
    return false
end

"""    apply_inputs!(drive, integ, t) -> Bool

Apply every sample due at `t` (within 1e-12 relative); `true` when a parameter changed."""
function apply_inputs!(drive::InputDrive, integ, t::Float64)
    tol = 1.0e-12 * max(1.0, abs(t))
    changed = false
    for (j, d) in enumerate(drive.inputs)
        k = drive.next[j]
        last = 0
        while k <= length(d.t) && d.t[k] <= t + tol
            last = k
            k += 1
        end
        drive.next[j] = k
        last == 0 && continue
        v = d.u[last]
        v == Float64(drive.getters[j](integ)) && continue
        drive.setters[j](integ, v)
        changed = true
    end
    changed || return false
    # As `run_tick!` publishes a held value: a parameter discontinuity, not a state jump.
    drive.dae && reinit_algebraic!(integ)
    ModelingToolkit.SciMLBase.reeval_internals_due_to_modification!(
        integ, false; callback_initializealg = ModelingToolkit.SciMLBase.NoInit()
    )
    return true
end

"""Merge the input change instants into the run targets (non-grid, non-tick targets)."""
function merge_input_targets(targets::Vector{RunTarget}, times::Vector{Float64})
    isempty(times) && return targets
    out = RunTarget[]
    i, j = 1, 1
    while i <= length(targets) || j <= length(times)
        if j > length(times)
            push!(out, targets[i]); i += 1
        elseif i > length(targets)
            push!(out, RunTarget(times[j], false, false, 0)); j += 1
        else
            a, b = targets[i].t, times[j]
            if abs(a - b) <= 1.0e-12 * max(1.0, abs(a))
                push!(out, targets[i]); i += 1; j += 1
            elseif a < b
                push!(out, targets[i]); i += 1
            else
                push!(out, RunTarget(b, false, false, 0)); j += 1
            end
        end
    end
    return out
end
