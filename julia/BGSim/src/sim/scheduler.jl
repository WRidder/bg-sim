# The discrete scheduler's runtime half (plan section 5.9, decision D3).
#
# `src/compile/discrete.jl` produces one [`Compile.DiscretePartition`](@ref) per `@discrete`
# scope, already qualified and topologically ordered. This file compiles those partitions into
# generated step functions and drives them around the continuous integrator:
#
#   1. `discrete_schedule(flat; t_start, t_end)` compiles every partition with
#      `RuntimeGeneratedFunctions` into `step!(dstate, inputs, params, t)`, collects the exact
#      integer-nanosecond tick times and which partitions are due at each of them.
#   2. `prepare_discrete!(schedule, model, integ)` builds the `SymbolicIndexingInterface`
#      getters once: `getu` for the continuous values the discrete code samples, `getp` for its
#      runtime parameters and for the held outputs (MTK discrete parameters, D4).
#   3. `run_tick!` samples the continuous inputs at the tick, snapshots the held values for
#      `previous(x)`, runs the due partitions in topological order and writes a changed held
#      output through `setp` + `derivative_discontinuity!(integ, true)`.
#
# The run loop itself stays in `src/sim/simulate.jl`; it merges the output grid with the tick
# times and records each changed tick as a left and a right row at the same `t`, through the
# same `record_event(t, side, values)` seam J2.3 uses for solver events.
#
# Generated code never contains a user name. `step_expression` emits array indices, literals,
# arithmetic and `GlobalRef`s into the private `DiscreteRuntime` module below; the expression
# is compiled by `RuntimeGeneratedFunctions`, not by `eval` of source text.

import RuntimeGeneratedFunctions

"""
    DiscreteRuntime

The private module that resolves the helper names of generated step functions. It contains
only the few functions the language needs that are not plain Base calls, with the same
semantics as the continuous lowering (`lower_nonsmooth` in `src/lower/fnmap.jl`).
"""
module DiscreteRuntime

# A discrete `Bool` may be stored as 1.0/0.0 in `dstate`, and a D18 temporary may be a Real
# used as a condition; both must behave like a Bool.
__truthy(x::Bool) = x
__truthy(x::Real) = !iszero(x)

__not(x) = !__truthy(x)

__ifelse(c, a, b) = ifelse(__truthy(c), a, b)

# The language's `round` is round-half-away-from-zero (plan 5.8 and `lower_nonsmooth`).
__round(x) = ifelse(x >= 0, floor(x + 0.5), ceil(x - 0.5))

# `sign` mirrors `lower_nonsmooth` exactly (`sign(-0.0)` is `0.0`, not `-0.0`).
__sign(x) = ifelse(x > 0, 1.0, ifelse(x < 0, -1.0, 0.0))

# `clamp(x, hi)` is `clamp(x, -hi, hi)`; `saturate` shares the spelling.
__clamp(x, hi) = ifelse(x < -hi, -hi, ifelse(x > hi, hi, x))
__clamp(x, lo, hi) = ifelse(x < lo, lo, ifelse(x > hi, hi, x))

__deadzone(x, hi) = __deadzone(x, -hi, hi)
__deadzone(x, lo, hi) = ifelse(x > hi, x - hi, ifelse(x < lo, x - lo, 0.0))

end # module DiscreteRuntime

RuntimeGeneratedFunctions.init(DiscreteRuntime)

# The two value holders the generated function sees. `prev` is this tick's snapshot, which is
# what `previous(x)` reads; it is a field instead of a fifth argument so the required
# `step!(dstate, inputs, params, t)` signature stays exactly as plan 5.9 specifies.
mutable struct DiscreteState
    values::Vector{Float64}
    prev::Vector{Float64}
    prev_t::Float64
end

mutable struct DiscreteValues
    values::Vector{Float64}
    prev::Vector{Float64}
end

"""    ScheduledPartition(partition, step, writes, input_indices, param_indices)

One compiled partition: its flat description, the generated step function, the indices in the
shared held-value vector that it writes, and the slots in the shared input/parameter vectors
that it samples."""
struct ScheduledPartition
    partition::Compile.DiscretePartition
    step::Any
    writes::Vector{Int}
    input_indices::Vector{Int}
    param_indices::Vector{Int}
end

"""    DiscreteSchedule

Everything about the discrete clocks that does not depend on the integrator: the ordered
partitions, the shared signal-id index maps, the exact tick times in the run span and the
partitions due at each tick."""
struct DiscreteSchedule
    partitions::Vector{ScheduledPartition}
    held_ids::Vector{String}
    held_index::Dict{String,Int}
    input_ids::Vector{String}
    input_index::Dict{String,Int}
    param_ids::Vector{String}
    param_index::Dict{String,Int}
    tick_ns::Vector{Int64}
    tick_times::Vector{Float64}
    due::Vector{Vector{Int}}
    base_ns::Int64
end

"""    discrete_schedule(flat; t_start = 0.0, t_end = 1.0) -> DiscreteSchedule

Compile the flat model's discrete partitions into step functions and build their tick grid.
The partitions are already in topological order (E105 is a compile-time error, so a flat
model with a cycle never reaches a run)."""
function discrete_schedule(
    flat::Flat.FlatModel;
    t_start::Real = 0.0,
    t_end::Real = 1.0,
)
    parts = Compile.DiscretePartition[flat.discrete...]
    isempty(parts) && throw(ArgumentError("the model has no discrete partitions"))

    held_ids = String[]
    for p in parts, id in p.writes
        id in held_ids || push!(held_ids, id)
    end
    held_index = Dict{String,Int}(id => i for (i, id) in enumerate(held_ids))

    input_ids = String[]
    param_ids = String[]
    is_parameter = Set{String}(String(p.id) for p in flat.parameters)
    for p in parts
        # `previous(x)` reads are excluded from the dependency edges (they see the value from
        # before this tick) but they still need an input/parameter slot in the runtime.
        for id in Iterators.flatten((p.reads, p.previous_reads))
            haskey(held_index, id) && continue
            if id in is_parameter
                id in param_ids || push!(param_ids, id)
            else
                id in input_ids || push!(input_ids, id)
            end
        end
    end
    input_index = Dict{String,Int}(id => i for (i, id) in enumerate(input_ids))
    param_index = Dict{String,Int}(id => i for (i, id) in enumerate(param_ids))

    scheduled = ScheduledPartition[]
    for p in parts
        ex = Compile.step_expression(
            p, held_index, input_index, param_index, DiscreteRuntime
        )
        fn = RuntimeGeneratedFunctions.RuntimeGeneratedFunction(
            DiscreteRuntime, DiscreteRuntime, ex
        )
        own_inputs = Int[
            input_index[id] for id in Iterators.flatten((p.reads, p.previous_reads)) if
            haskey(input_index, id)
        ]
        own_params = Int[
            param_index[id] for id in Iterators.flatten((p.reads, p.previous_reads)) if
            haskey(param_index, id)
        ]
        push!(
            scheduled,
            ScheduledPartition(
                p, fn, [held_index[id] for id in p.writes],
                unique!(own_inputs), unique!(own_params),
            ),
        )
    end

    tick_ns, due = _tick_grid(parts, Float64(t_start), Float64(t_end))
    tick_times = Float64[Float64(ns) / 1.0e9 for ns in tick_ns]
    base = Int64(0)
    for p in parts
        base = base == 0 ? p.period_ns : gcd(base, p.period_ns)
    end
    return DiscreteSchedule(
        scheduled, held_ids, held_index, input_ids, input_index, param_ids,
        param_index, tick_ns, tick_times, due, base,
    )
end

# All tick instants strictly inside `(t_start, t_end]`, as exact nanoseconds, and for each one
# the indices of the partitions that are due there (in topological order). A tick at
# `t_start` is the initial state, not an execution: the plan's loop steps before it ticks, so
# the first execution is the first tick after the start.
function _tick_grid(parts, t_start::Float64, t_end::Float64)
    start_ns = t_start * 1.0e9
    end_ns = t_end * 1.0e9
    ticks = Int64[]
    for p in parts
        p.period_ns > 0 || continue
        k0 = max(Int64(0), ceil(Int64, (start_ns - p.offset_ns) / p.period_ns))
        k = k0
        while true
            ns = p.offset_ns + k * p.period_ns
            ns > end_ns && break
            if ns > start_ns + 1.0e-6
                push!(ticks, ns)
            end
            k += 1
        end
    end
    sort!(ticks)
    unique!(ticks)
    due = Vector{Int}[]
    for ns in ticks
        at = Int[]
        for (i, p) in enumerate(parts)
            p.period_ns > 0 || continue
            ns >= p.offset_ns || continue
            (ns - p.offset_ns) % p.period_ns == 0 && push!(at, i)
        end
        push!(due, at)
    end
    return ticks, due
end

"""    DiscreteRun

The live state of one scheduled run: the generated functions, the shared vectors, the
`getu`/`getp` getters and the `setp` setter for the held outputs."""
mutable struct DiscreteRun
    schedule::DiscreteSchedule
    state::DiscreteState
    inputs::DiscreteValues
    params::Vector{Float64}
    input_getters::Vector{Any}
    param_getters::Vector{Any}
    setter::Any
end

"""    prepare_discrete!(schedule, model, integ, t_start) -> DiscreteRun

Build the getters and the held-value setter once, and initialise the held values from the
integrator's parameters (their declared start values, D4)."""
function prepare_discrete!(
    schedule::DiscreteSchedule,
    model::CompiledModel,
    integ,
    t_start::Float64,
)
    input_getters = Any[]
    for id in schedule.input_ids
        sym = get(model.vars, id, nothing)
        sym === nothing &&
            throw(LowerError("the discrete code samples `$id`, which has no lowered signal",
                nothing))
        push!(input_getters, getu(integ, sym))
    end
    param_getters = Any[]
    for id in schedule.param_ids
        sym = get(model.params, id, nothing)
        sym === nothing &&
            throw(LowerError("the discrete code reads parameter `$id`, which is not lowered",
                nothing))
        push!(param_getters, getp(integ, sym))
    end
    held_symbols = Num[]
    for id in schedule.held_ids
        sym = get(model.params, id, nothing)
        sym === nothing &&
            throw(LowerError("the held discrete value `$id` is not a parameter of the compiled model",
                nothing))
        push!(held_symbols, sym)
    end
    values = Float64[Float64(getp(integ, sym)(integ)) for sym in held_symbols]
    state = DiscreteState(copy(values), copy(values), t_start)
    inputs = DiscreteValues(zeros(length(schedule.input_ids)), zeros(length(schedule.input_ids)))
    params = zeros(length(schedule.param_ids))
    setter = isempty(held_symbols) ? nothing : setp(integ, held_symbols)
    return DiscreteRun(
        schedule, state, inputs, params, input_getters, param_getters, setter
    )
end

"""    run_tick!(run, integ, t, tick_index) -> Bool

Execute every partition due at the tick `t` (index `tick_index` in the schedule), in
topological order, and write the held outputs back through `setp`. Returns `true` when a held
output changed, which is when the run loop records the left/right pair at `t`.

The operation order is the contract for bit-exactness:
  * the previous-tick snapshot (for `previous(x)`) is taken once, before any partition runs;
  * each partition samples its continuous inputs and runtime parameters immediately before it
    runs, so a partition that comes later in the topological order sees the held outputs an
    earlier one wrote in the same tick through a signal connection;
  * partitions run in the order `discrete_schedule` stored (topological), and a direct read of
    a held value sees the value written earlier in the same tick.
"""
function run_tick!(run::DiscreteRun, integ, t::Float64, tick_index::Int)
    # The pre-tick snapshot of everything `previous(x)` may read: the continuous values as
    # they were at the end of the previous tick, and the held outputs before this tick.
    copyto!(run.inputs.prev, run.inputs.values)
    copyto!(run.state.prev, run.state.values)
    run.state.prev_t = t
    held_before = copy(run.state.prev)

    for i in run.schedule.due[tick_index]
        p = run.schedule.partitions[i]
        # Sample this partition's continuous inputs now, so a partition that runs later in the
        # same tick sees the held outputs an earlier one wrote through a signal connection.
        for j in p.input_indices
            run.inputs.values[j] = Float64(run.input_getters[j](integ))
        end
        for j in p.param_indices
            run.params[j] = Float64(run.param_getters[j](integ))
        end
        p.step(run.state, run.inputs, run.params, t)
        # Publish this partition's held outputs before the next partition runs (D4:
        # `setp` + `derivative_discontinuity!`, never a state write).
        published = false
        for k in p.writes
            if run.state.values[k] != held_before[k]
                held_before[k] = run.state.values[k]
                published = true
            end
        end
        if published && run.setter !== nothing
            run.setter(integ, run.state.values)
            ModelingToolkit.SciMLBase.derivative_discontinuity!(integ, true)
        end
    end
    # Re-sample every read input once more: `previous(x)` at the next tick must see the value
    # x had after this tick finished, not the one it had when the partition that reads it last
    # sampled. The snapshot at the start of the next `run_tick!` copies these values.
    for j in eachindex(run.input_getters)
        run.inputs.values[j] = Float64(run.input_getters[j](integ))
    end
    return any(k -> run.state.values[k] != run.state.prev[k], eachindex(run.state.values))
end

# ---------------------------------------------------------------------------------------
# Merging the output grid with the tick grid
# ---------------------------------------------------------------------------------------

"""    RunTarget(t, grid, tick, tick_index)

One place the run loop must land: an output-grid time, a discrete tick, or both. `tick_index`
is the index into `DiscreteSchedule.tick_times`/`due` (`0` when not a tick)."""
struct RunTarget
    t::Float64
    grid::Bool
    tick::Bool
    tick_index::Int
end

"""    discrete_targets(grid, schedule) -> Vector{RunTarget}

Merge the output grid (from `grid[2]` on; row zero is written before the loop) with the tick
times. A grid time and a tick less than 1e-12 apart become one target that is both."""
function discrete_targets(grid::Vector{Float64}, run::Union{Nothing,DiscreteRun})
    out = RunTarget[]
    gi = 2
    n = length(grid)
    times = run === nothing ? Float64[] : run.schedule.tick_times
    ti = 1
    m = length(times)
    while gi <= n || ti <= m
        g = gi <= n ? grid[gi] : Inf
        tk = ti <= m ? times[ti] : Inf
        tolerance = 1.0e-12 * max(1.0, abs(g == Inf ? tk : g))
        if g == Inf && tk == Inf
            break
        elseif tk == Inf
            push!(out, RunTarget(g, true, false, 0))
            gi += 1
        elseif g == Inf
            push!(out, RunTarget(tk, false, true, ti))
            ti += 1
        elseif abs(g - tk) <= tolerance
            push!(out, RunTarget(g, true, true, ti))
            gi += 1
            ti += 1
        elseif g < tk
            push!(out, RunTarget(g, true, false, 0))
            gi += 1
        else
            push!(out, RunTarget(tk, false, true, ti))
            ti += 1
        end
    end
    return out
end

export DiscreteSchedule, DiscreteRun, RunTarget

