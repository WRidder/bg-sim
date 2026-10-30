# `@events` with `reinit` in the fixed-step export (plan/EXPORT_PLAN.md J-EX6, D-EX8).
#
# The simulator fires an event when its zero-crossing expression `z` (D19: `a < b` is
# `b - a`) rises through zero inside a solver step: `z < 0` at the start of the step and
# `z >= 0` at its end. Only the upward edge has an affect. A condition that is zero or
# positive at the start of a step does not fire, so a condition that is already true at
# t_start, or that stays true after its event, fires only after it has gone negative again.
# This is DiffEq's `prev_sign < 0 && prev_sign * next_sign <= 0`.
#
# The export checks the same edge once per internal step and does not locate the crossing:
#
#   1. at the start of the step, `bg_event_conditions` evaluates every `z` (after the
#      previous step's events and discrete tick, with the current inputs and parameters);
#   2. the step is integrated;
#   3. `bg_events` evaluates every `z` at the end of the step and applies the `reinit` of each
#      event whose `z` crossed upward, in declaration order. All assignments of one event
#      read the state before that event (the simulator's simultaneous `reinit`); a later
#      event reads the state the earlier ones left;
#   4. the discrete partitions due at the end of the step run (`bg_tick`), so they sample
#      the state after the `reinit`. The simulator has the same order: a tick at `t` runs
#      after every event up to and including `t`.
#
# So an event fires up to one `dt` late (W203 per event). Events that cross in the same step
# fire in declaration order, not in the order of their crossing instants.
#
# Supported targets are the states of the compiled system. Everything else (a parameter
# written by an event, a target the compiler eliminated, an `int` inside an event) is
# refused with E110 naming the event's block and source range.

"""    EventExportError(message, origin)

An `@events` construct the export cannot lower; `export_model` reports it as E110 at the
event's origin."""
struct EventExportError <: Exception
    message::String
    origin::Any
end

Base.showerror(io::IO, e::EventExportError) = print(io, e.message)

"""One `@events` entry lowered against the compiled system."""
struct ExportEvent
    condition::Any          # the zero-crossing expression; an upward crossing fires
    targets::Vector{Int}    # 1-based state indices, in assignment order
    values::Vector{Any}     # the new values, all read from the state before the event
    label::String           # the source condition, for comments and diagnostics
    origin::Any             # Flat.Origin of the `@events` entry
end

"""    lower_events(flat, model, xs) -> Vector{ExportEvent}

Lower every `@events` entry of `flat` with the compiled model's own variable maps, so the
symbols are the ones of `model.system`. The flat actions are already fully substituted
(`Compile._subst_event`), so every plain read is the value before the event."""
function lower_events(flat::Flat.FlatModel, model, xs)
    out = ExportEvent[]
    isempty(flat.events) && return out
    ctx = BGSim.LowerCtx(model.vars, model.params)
    for ev in flat.events
        ev isa Compile.FlatEvent || continue
        label = sprint(show, ev.condition)
        fail(msg) = throw(EventExportError(msg, ev.origin))
        ctx.origin = ev.origin
        ctx.event_values = nothing
        lower(e) = try
            Symbolics.unwrap(BGSim.lower_expression(e, ctx))
        catch err
            err isa LowerError || rethrow()
            fail("the `@events` entry `$label` cannot be lowered for the export: $(err.message)")
        end
        cond = lower(ev.zero_crossing)
        targets = Int[]
        values = Any[]
        for (id, e) in ev.actions
            v = get(model.vars, id, nothing)
            if v === nothing
                haskey(model.params, id) &&
                    fail("the `@events` entry `$label` writes the parameter `$id`; events that write parameters are not exported yet")
                fail("the `@events` entry `$label` writes `$id`, which has no variable in the compiled system")
            end
            k = findfirst(x -> isequal(x, Symbolics.unwrap(v)), xs)
            k === nothing &&
                fail("the `@events` entry `$label` reinits `$id`, which the compiled system does not keep as a state")
            push!(targets, k)
            push!(values, lower(e))
        end
        isempty(ctx.int_states) ||
            fail("the `@events` entry `$label` uses `int`, which is not exported inside an event")
        push!(out, ExportEvent(cond, targets, values, label, ev.origin))
    end
    return out
end

"""    emit_events(io, events, env, obs, names_x)

The event code of `model.c`: `bg_event_conditions` (every zero-crossing value), one
`bg_event_<k>` per event (its new values into a scratch array), and `bg_events`, which
`bg_step` calls after the integration step. Conditions and values use live `ifelse`, never
the frozen modes: they are evaluated at one instant."""
function emit_events(io, events, env, obs, names_x)
    println(io, "/* Event conditions: event k fires when z[k] crosses zero upward within a step,")
    println(io, "   from z[k] < 0 at its start to z[k] >= 0 at its end (see bg_events). */")
    emit_function(io, "void bg_event_conditions(const bg_model *m, double t, const double *x, double *z)",
        [("z[$(k - 1)]", ev.condition, ev.label) for (k, ev) in enumerate(events)], env, obs)
    for (k, ev) in enumerate(events)
        println(io, "/* Event $(k - 1): $(ccomment(ev.label)) in $(ccomment(something(ev.origin.path, "(root)"))). */")
        emit_function(io, "static void bg_event_$(k - 1)(const bg_model *m, double t, const double *x, double *r)",
            [("r[$(j - 1)]", v, names_x[ev.targets[j]]) for (j, v) in enumerate(ev.values)], env, obs)
    end
    println(io, "/* After an internal step that ends at t: apply every event whose condition crossed upward")
    println(io, "   in the step, in declaration order. An event reads the state left by the earlier ones;")
    println(io, "   its own assignments all read the state before it. Returns the number fired. */")
    println(io, "int bg_events(bg_model *m, double t) {")
    if isempty(events)
        println(io, "    (void)m; (void)t;\n    return 0;\n}\n")
        return
    end
    println(io, "    int fired = 0;")
    println(io, "    bg_event_conditions(m, t, m->x, m->ez);")
    for (k, ev) in enumerate(events)
        println(io, "    if (m->ez0[$(k - 1)] < 0.0 && m->ez[$(k - 1)] >= 0.0) {")
        println(io, "        bg_event_$(k - 1)(m, t, m->x, m->er);")
        for (j, i) in enumerate(ev.targets)
            println(io, "        m->x[$(i - 1)] = m->er[$(j - 1)]; /* $(ccomment(names_x[i])) */")
        end
        println(io, "        ++fired;")
        println(io, "    }")
    end
    println(io, "    return fired;\n}\n")
end
