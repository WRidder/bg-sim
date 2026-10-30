# The watch pool, `debug.evaluate` and `debug.values` (plan 5.13, decisions D22 and D27; work
# package J4.3).
#
# One `VectorContinuousCallback` with 16 slots is installed in every debug run (the marked
# insertion point `_dbg_init_kwargs` in `simulate.jl`; `init` merges a `callback` keyword with
# the callbacks MTK put into the problem, see NOTES.md "J4.3"). Slot `i` evaluates `c_i(u, p, t)`,
# compiled once per watch from the watch AST with `SymbolicIndexingInterface.observed(sys, expr)`
# (so a variable that `mtkcompile` eliminated can be watched). A disabled or empty slot returns
# `1.0`. The affect only marks the slot of an **upward** crossing; the pause itself happens in
# the after-step checkpoint (`dbg_after_step!` calls `_watch_hit`), so the integrator is never
# blocked inside a callback.
#
# Changing the pool needs no recompile of the problem: `DiffEqBase` evaluates the condition at
# `tprev` again in every step (no cached previous condition), so a new or changed slot starts
# from the current state and cannot report a crossing that happened before it existed.
#
# `debug.evaluate` (D27) runs the constant-folding interpreter of the front end over a resolved
# watch expression, with signal lookups through the live integrator and, at a statement pause,
# the names of the paused frame. It is read-only and never calls `eval`.

import SymbolicIndexingInterface

const WATCH_SLOT_COUNT = 16

# One compiled watch: everything the pool and the status need, keyed by (text, context).
struct CompiledWatch
    text::String
    context::Union{Nothing,String}
    expr::Any             # the parsed AST (for its range)
    resolved::Any         # names resolved to `SignalRef`s
    condition::Any        # the real expression whose upward zero crossing is the event
    fn::Any               # (u, p, t) -> Real
    signals::Vector{String}
end

"""
    WatchPool

The 16 slots of the watch callback of one debug run (`ctx.ext[:watch]`): the compiled
condition function, the owning breakpoint id, the `hitCount` target and the hit counter of
each slot, plus the slots the affect marked since the last checkpoint."""
mutable struct WatchPool
    fns::Vector{Any}
    bp_ids::Vector{Union{Nothing,String}}
    targets::Vector{Union{Nothing,Int}}
    hits::Vector{Int}
    keys::Vector{Any}
    locations::Vector{Any}
    fired::Vector{Int}
    errors::Vector{Union{Nothing,String}}
    compiled::Dict{Tuple{String,Union{Nothing,String}},Any}
    callback::Any
end

function WatchPool(; interp_points::Int = 10)
    pool = WatchPool(
        Any[nothing for _ in 1:WATCH_SLOT_COUNT],
        Union{Nothing,String}[nothing for _ in 1:WATCH_SLOT_COUNT],
        Union{Nothing,Int}[nothing for _ in 1:WATCH_SLOT_COUNT],
        zeros(Int, WATCH_SLOT_COUNT),
        Any[nothing for _ in 1:WATCH_SLOT_COUNT],
        Any[nothing for _ in 1:WATCH_SLOT_COUNT],
        Int[],
        Union{Nothing,String}[nothing for _ in 1:WATCH_SLOT_COUNT],
        Dict{Tuple{String,Union{Nothing,String}},Any}(),
        nothing,
    )
    pool.callback = ModelingToolkit.SciMLBase.VectorContinuousCallback(
        _WatchCondition(pool), _WatchAffect(pool), WATCH_SLOT_COUNT;
        rootfind = ModelingToolkit.SciMLBase.RightRootFind,
        save_positions = (false, false), interp_points = interp_points,
    )
    return pool
end

struct _WatchCondition
    pool::WatchPool
end

# A watch whose function throws (for example `sqrt` of a negative number) reports NaN, which
# never crosses zero; the first message is kept in `pool.errors[i]`.
function _watch_value(pool::WatchPool, i::Int, f, u, p, t)
    try
        return Float64(f(u, p, t))
    catch err
        pool.errors[i] === nothing && (pool.errors[i] = sprint(showerror, err))
        return NaN
    end
end

function (c::_WatchCondition)(out, u, t, integ)
    pool = c.pool
    fns = pool.fns
    p = integ.p
    @inbounds for i in 1:WATCH_SLOT_COUNT
        f = fns[i]
        out[i] = f === nothing ? 1.0 : _watch_value(pool, i, f, u, p, t)
    end
    return nothing
end

struct _WatchAffect
    pool::WatchPool
end

# `events[i] > 0` is an upward crossing (the condition was negative before), `< 0` a downward
# one, which a watch ignores. The affect leaves the state alone, so it is not a derivative
# discontinuity (no re-evaluation of the integrator internals).
function (a::_WatchAffect)(integ, events)
    pool = a.pool
    for i in 1:WATCH_SLOT_COUNT
        events[i] > 0 || continue
        pool.fns[i] === nothing && continue
        pool.hits[i] += 1
        target = pool.targets[i]
        (target === nothing || pool.hits[i] == target) && push!(pool.fired, i)
    end
    ModelingToolkit.SciMLBase.derivative_discontinuity!(integ, false)
    return nothing
end

"""    watch_pool(ctx) -> Union{Nothing,WatchPool}

The watch pool of a debug run (`nothing` before the run has started)."""
watch_pool(ctx::DebugCtx) = get(ctx.ext, :watch, nothing)

"""    watch_hits(ctx) -> Dict{String,Int}

The hit count of every watch breakpoint that currently owns a slot."""
function watch_hits(ctx::DebugCtx)
    pool = watch_pool(ctx)
    out = Dict{String,Int}()
    pool === nothing && return out
    for i in 1:WATCH_SLOT_COUNT
        id = pool.bp_ids[i]
        id === nothing || (out[id] = pool.hits[i])
    end
    return out
end

"""    watch_errors(ctx) -> Dict{String,String}

The first evaluation error of every watch whose condition threw while it was evaluated."""
function watch_errors(ctx::DebugCtx)
    pool = watch_pool(ctx)
    out = Dict{String,String}()
    pool === nothing && return out
    for i in 1:WATCH_SLOT_COUNT
        id = pool.bp_ids[i]
        msg = pool.errors[i]
        (id === nothing || msg === nothing) || (out[id] = msg)
    end
    return out
end

# ---------------------------------------------------------------------------------------
# The insertion points of `simulate` and `dbg_after_step!`
# ---------------------------------------------------------------------------------------

# `init` gets the pool as its `callback` keyword (merged with the problem's callbacks).
_dbg_init_kwargs(::Nothing, kwargs) = kwargs

function _dbg_init_kwargs(ctx::DebugCtx, kwargs)
    pool = WatchPool()
    ctx.ext[:watch] = pool
    return merge(kwargs, (; callback = pool.callback))
end

# After a step: the first watch the affect marked, or `nothing`. Always clears the marks.
function _watch_hit(ctx::DebugCtx)
    pool = get(ctx.ext, :watch, nothing)
    (pool === nothing || isempty(pool.fired)) && return nothing
    hit = nothing
    for i in pool.fired
        id = pool.bp_ids[i]
        id === nothing && continue
        hit === nothing && (hit = (id = id, location = pool.locations[i]))
    end
    empty!(pool.fired)
    return hit
end

# ---------------------------------------------------------------------------------------
# The scope of a run
# ---------------------------------------------------------------------------------------

struct WatchBase
    signals::Dict{String,Any}      # id -> Units.Dims or nothing
    types::Dict{String,Symbol}
    labels::Dict{String,Union{Nothing,String}}   # id -> unit text of the signal list
    refs::Dict{String,String}      # instance path -> block ref
end

function _watch_base(s::DebugSession)
    cached = get(s.ctx.ext, :watch_base, nothing)
    cached === nothing || return cached
    flat = s.flat
    model = s.lowered
    signals = Dict{String,Any}()
    types = Dict{String,Symbol}()
    for v in flat.variables
        signals[v.id] = v.unit
        types[v.id] = v.type
    end
    for p in flat.parameters
        signals[p.id] = p.unit
        types[p.id] = p.type
    end
    for d in flat.derived
        signals[d.id] = d.unit
        types[d.id] = d.type
    end
    # Only what the lowering can read is a valid signal.
    for id in collect(keys(signals))
        (haskey(model.vars, id) || haskey(model.params, id)) || delete!(signals, id)
    end
    for id in keys(model.vars)
        haskey(signals, id) || (signals[id] = nothing)
    end
    for id in keys(model.params)
        haskey(signals, id) || (signals[id] = nothing)
    end
    labels = Dict{String,Union{Nothing,String}}()
    for sig in flat.signals
        labels[String(sig.id)] = sig.unit === nothing ? nothing : String(sig.unit)
    end
    refs = Dict{String,String}(String(i.path) => String(i.ref) for i in flat.instances)
    base = WatchBase(signals, types, labels, refs)
    s.ctx.ext[:watch_base] = base
    return base
end

_watch_scope(base::WatchBase, context, locals = Symbol[]) =
    WatchScope(base.signals; types = base.types, context = context, locals = locals)

_diag_tuples(diags) = Any[to_namedtuple(d) for d in diags]

# ---------------------------------------------------------------------------------------
# Compiling one watch
# ---------------------------------------------------------------------------------------

function _compile_watch(s::DebugSession, base::WatchBase, text::String,
    context::Union{Nothing,String})
    pool = s.ctx.ext[:watch]
    cached = get(pool.compiled, (text, context), nothing)
    cached === nothing || return cached
    result = _compile_watch_uncached(s, base, text, context)
    pool.compiled[(text, context)] = result
    return result
end

# Returns a `CompiledWatch` or the diagnostics that refuse the watch.
function _compile_watch_uncached(s::DebugSession, base::WatchBase, text::String,
    context::Union{Nothing,String})
    expr, diags = parse_watch(text)
    expr === nothing && return diags
    resolved, ty, dims, check = check_watch(expr, _watch_scope(base, context))
    resolved === nothing && return check
    cond, cond_diags = watch_condition(resolved)
    cond === nothing && return vcat(check, cond_diags)
    model = s.lowered
    num = try
        lower_expression(flat_names(cond), LowerCtx(model.vars, model.params))
    catch err
        err isa LowerError || rethrow()
        return Diagnostic[diag(
            "E900", "the watch `$text` cannot be lowered: $(err.message)"; scope = "watch",
        )]
    end
    fn = if Symbolics.unwrap(num) isa Number
        value = Float64(Symbolics.unwrap(num))
        (u, p, t) -> value
    else
        SymbolicIndexingInterface.observed(model.system, num)
    end
    return CompiledWatch(text, context, expr, resolved, cond, fn, unique(signal_refs(resolved)))
end

function _watch_location(base::WatchBase, w::CompiledWatch)
    r = expr_range(w.expr)
    path = w.context === nothing ? "" : w.context
    return (
        path = path, ref = get(base.refs, path, ""), scope = "watch",
        range = (line = r.line, col = r.col, endLine = r.endLine, endCol = r.endCol),
    )
end

# ---------------------------------------------------------------------------------------
# The "watch" breakpoint kind
# ---------------------------------------------------------------------------------------

function _validate_watch(data, raw)
    expr = get(data, "expr", nothing)
    expr isa AbstractString ||
        throw(ArgumentError("a watch breakpoint needs a string `watch.expr`"))
    context = get(data, "context", nothing)
    context === nothing || context isa AbstractString ||
        throw(ArgumentError("`watch.context` must be a string or null"))
    return nothing
end

_watch_context(bp::Breakpoint) = begin
    c = get(bp.data, "context", nothing)
    c === nothing || isempty(strip(String(c))) ? nothing : String(strip(String(c)))
end

function _too_many_watches()
    return diag(
        "E001", "at most $WATCH_SLOT_COUNT watch breakpoints";
        hint = "disable or remove a watch breakpoint, then set the list again",
        scope = "watch",
    )
end

function _syntax_status(bp::Breakpoint)
    expr, diags = parse_watch(String(bp.data["expr"]))
    return breakpoint_status(bp; verified = expr !== nothing, diagnostics = _diag_tuples(diags))
end

function _resolve_watches!(ctx::DebugCtx, s::Union{Nothing,DebugSession}, bps::Vector{Breakpoint})
    pool = get(ctx.ext, :watch, nothing)
    if s === nothing || pool === nothing
        # Before the run exists only the syntax can be checked; the names are resolved when
        # the run starts (the resolver runs again then).
        return NamedTuple[_syntax_status(bp) for bp in bps]
    end
    base = _watch_base(s)
    saved = Dict{String,Tuple{Any,Int}}()
    for i in 1:WATCH_SLOT_COUNT
        id = pool.bp_ids[i]
        id === nothing || (saved[id] = (pool.keys[i], pool.hits[i]))
    end
    fill!(pool.fns, nothing)
    fill!(pool.bp_ids, nothing)
    fill!(pool.targets, nothing)
    fill!(pool.keys, nothing)
    fill!(pool.locations, nothing)
    fill!(pool.errors, nothing)
    fill!(pool.hits, 0)
    empty!(pool.fired)
    used = 0
    out = NamedTuple[]
    for bp in bps
        text = String(bp.data["expr"])
        context = _watch_context(bp)
        w = try
            _compile_watch(s, base, text, context)
        catch err
            Diagnostic[diag(
                "E900", "the watch `$text` could not be compiled: " * sprint(showerror, err);
                scope = "watch",
            )]
        end
        if !(w isa CompiledWatch)
            push!(out, breakpoint_status(bp; verified = false, diagnostics = _diag_tuples(w)))
            continue
        end
        paths = context === nothing ? String[] : String[context]
        if bp.enabled
            if used >= WATCH_SLOT_COUNT
                push!(out, breakpoint_status(
                    bp; verified = false, diagnostics = _diag_tuples([_too_many_watches()]),
                ))
                continue
            end
            used += 1
            key = (text, context)
            pool.fns[used] = w.fn
            pool.bp_ids[used] = bp.id
            pool.targets[used] = bp.hit_count
            pool.keys[used] = key
            pool.locations[used] = _watch_location(base, w)
            old = get(saved, bp.id, nothing)
            old !== nothing && old[1] == key && (pool.hits[used] = old[2])
        end
        push!(out, breakpoint_status(bp; verified = true, hooks = 1, paths = paths))
    end
    return out
end

register_breakpoint_kind!("watch", _resolve_watches!; validate = _validate_watch)

# ---------------------------------------------------------------------------------------
# Reading values at a pause
# ---------------------------------------------------------------------------------------

# Per-signal getters, built on first use with the recorder's lookup (`vars`, then `params`).
# The recorder itself reads all signals at once through PERF-1's `SignalReader`, which has no
# per-signal entry points.
function _getter_cache(s::DebugSession)
    cache = get(s.ctx.ext, :watch_getters, nothing)
    cache === nothing || return cache
    cache = Dict{String,Any}()
    s.ctx.ext[:watch_getters] = cache
    return cache
end

function _signal_getter(s::DebugSession, id::String)
    cache = _getter_cache(s)
    g = get(cache, id, nothing)
    g === nothing || return g
    model = s.lowered
    sym = get(model.vars, id, nothing)
    sym === nothing && (sym = get(model.params, id, nothing))
    sym === nothing && throw(ArgumentError("unknown signal `$id`"))
    g = ModelingToolkit.isparameter(sym) ? getp(s.integ, sym) : getu(s.integ, sym)
    cache[id] = g
    return g
end

function _signal_value(s::DebugSession, id::String)
    v = Float64(_signal_getter(s, id)(s.integ))
    ty = get(_watch_base(s).types, id, :Real)
    ty === :Bool && return v != 0
    ty === :Int && return Int(round(v))
    return v
end

"""
    WatchEnv(session, frame)

The environment of `debug.evaluate`: the names of the paused statement frame (`frame`, a
`Dict{Symbol,Any}` or `nothing`), `t`, and signals through [`SignalRef`](@ref)."""
struct WatchEnv <: AbstractDict{Symbol,Any}
    session::DebugSession
    frame::Union{Nothing,Dict{Symbol,Any}}
end

Base.haskey(env::WatchEnv, k::Symbol) =
    (env.frame !== nothing && haskey(env.frame, k)) || k === :t
Base.getindex(env::WatchEnv, k::Symbol) =
    env.frame !== nothing && haskey(env.frame, k) ? env.frame[k] :
    k === :t ? Float64(env.session.integ.t) : throw(KeyError(k))
Base.length(env::WatchEnv) = (env.frame === nothing ? 0 : length(env.frame)) + 1
Base.iterate(env::WatchEnv, args...) =
    iterate(env.frame === nothing ? Dict{Symbol,Any}() : env.frame, args...)

eval_const(e::SignalRef, env::WatchEnv) = _signal_value(env.session, e.id)

# ---------------------------------------------------------------------------------------
# debug.values
# ---------------------------------------------------------------------------------------

"""
    debug_values(ctx, ids) -> (; t, values)

`debug.values`: the value of every signal in `ids` at the pause (any signal id of the model,
recorded or not, including parameters and eliminated variables). Throws `DebugStateError`
when the run is not paused and `ArgumentError` for an unknown id."""
function debug_values(ctx::DebugCtx, ids)
    wanted = String[String(i) for i in ids]
    return with_paused(ctx) do s
        values = Dict{String,Float64}()
        for id in wanted
            values[id] = Float64(_signal_getter(s, id)(s.integ))
        end
        return (; t = Float64(s.integ.t), values = values)
    end
end

# ---------------------------------------------------------------------------------------
# debug.evaluate
# ---------------------------------------------------------------------------------------

_value_type(v::Bool) = "Bool"
_value_type(v::Integer) = "Int"
_value_type(v::AbstractArray) = isempty(v) ? "Real" : _value_type(first(v))
_value_type(v) = "Real"

_value_json(v::Bool) = v
_value_json(v::Integer) = v
_value_json(v::Real) = Float64(v)
_value_json(v::AbstractVector) = Any[_value_json(x) for x in v]
_value_json(v::AbstractMatrix) = Any[Any[_value_json(v[i, j]) for j in axes(v, 2)] for i in axes(v, 1)]

_value_size(v::AbstractArray) = collect(Int, size(v))
_value_size(v) = Int[]

function _evaluate_failure(diags)
    return (
        value = 0.0, type = "Real", size = Int[], unit = nothing,
        diagnostics = _diag_tuples(diags),
    )
end

"""
    debug_evaluate(ctx, expr, context = nothing) -> NamedTuple

`debug.evaluate` (D27): evaluate `expr` in the `watch` scope at the pause and return
`(; value, type, size, unit, diagnostics)` (the `evaluateResult` of the debug contract). Names
resolve in the paused statement's frame first (a statement pause), then relative to `context`,
then as model-level ids; `s"Motor1/i"` is any signal id. An error is an E001 to E006
diagnostic with `scope = "watch"` and the value `0.0`. Throws `DebugStateError` when the run is
not paused."""
function debug_evaluate(ctx::DebugCtx, expr::AbstractString, context = nothing)
    text = String(expr)
    ctxpath = context === nothing || isempty(strip(String(context))) ? nothing :
              String(strip(String(context)))
    return with_paused(ctx) do s
        return _evaluate(s, text, ctxpath)
    end
end

function _evaluate(s::DebugSession, text::String, context::Union{Nothing,String})
    parsed, diags = parse_watch(text)
    parsed === nothing && return _evaluate_failure(diags)
    base = _watch_base(s)
    frame = get(s.ctx.ext, :frame, nothing)
    frame_env = frame === nothing ? nothing : frame.env
    locals = frame_env === nothing ? Symbol[] : collect(keys(frame_env))
    resolved, ty, dims, check = check_watch(parsed, _watch_scope(base, context, locals))
    resolved === nothing && return _evaluate_failure(check)
    env = WatchEnv(s, frame_env)
    value = try
        eval_const(resolved, env)
    catch err
        if err isa ConstFoldError || err isa DomainError || err isa BoundsError ||
           err isa DivideError
            message = err isa ConstFoldError ? err.message : sprint(showerror, err)
            return _evaluate_failure(vcat(check, Diagnostic[_watch_diag(
                "E004", "`$text` cannot be evaluated: $message", expr_range(parsed);
                hint = "check the values it reads at this pause",
            )]))
        end
        rethrow()
    end
    unit = if value isa Bool
        nothing
    elseif resolved isa SignalRef
        get(base.labels, resolved.id, dims === nothing ? nothing : Units.unit_string(dims))
    else
        dims === nothing ? nothing : Units.unit_string(dims)
    end
    return (
        value = _value_json(value), type = _value_type(value), size = _value_size(value),
        unit = unit, diagnostics = _diag_tuples(check),
    )
end


export watch_pool, watch_hits, watch_errors, debug_evaluate, debug_values, WatchEnv
