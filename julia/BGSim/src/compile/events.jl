# Events and nonsmooth switching (plan sections 5.8, 9.2 and decisions D14/D19).
#
# Two jobs live here:
#
#   1. `@events` extraction. Every `cond => begin ... end` of a block becomes one
#      [`FlatEvent`](@ref) on the flat model, with fully qualified signal ids and the
#      condition already normalised to the real expression whose **upward** zero crossing
#      fires it (D19: `a < b` is `b - a`, `a > b` is `a - b`). The body is executed
#      sequentially at compile time and reduced to a final `target => value` map; event
#      bodies are imperative (D18 temporaries, `if`, `for`), so later assignments see the
#      values assigned earlier in the same body. The lowering in `lower/mtk.jl` turns the
#      map into one `SymbolicContinuousCallback` with `Pre(...)` reads for every state that
#      was not written earlier (the `Pair` form would wrap the whole right-hand side).
#
#   2. The switching conditions of the nonsmooth functions. `fnmap.jl` rewrites `abs`,
#      `sign`, `min`, `max`, `clamp`, `round`, `saturate` and `deadzone` into explicit
#      `ifelse` expressions, but ModelingToolkit adds no callback for an `ifelse`; the
#      collector below walks the flat expressions and returns one condition per kink.
#      `lower/mtk.jl` turns each into a condition-only `SymbolicContinuousCallback(c ~ 0)`.
#
# Both collectors work on the front-end AST, never on Symbolics internals, so they are
# testable without MTK and cannot be confused by `mtkcompile`'s rewriting.

# ---------------------------------------------------------------------------------------
# Flat @events
# ---------------------------------------------------------------------------------------

"""    FlatEvent(condition, zero_crossing, actions, origin, range)

One lowered `@events` entry. `condition` is the source condition (for diagnostics),
`zero_crossing` the real expression whose upward zero crossing fires the event (D19),
`actions` the final `target signal id => value` map of the body in execution order, and
`origin`/`range` the provenance inside the block."""
struct FlatEvent
    condition::BGSim.Expr
    zero_crossing::BGSim.Expr
    actions::Vector{Pair{String,BGSim.Expr}}
    origin::Flat.Origin
    range::SourceRange
end

function Base.show(io::IO, e::FlatEvent)
    print(io, "event(", sprint(show, e.zero_crossing), " => ")
    for (target, value) in e.actions
        print(io, target, '=', sprint(show, value), ';')
    end
    print(io, ')')
    return nothing
end

"""    EventEnv

The sequential environment of one `@events` body: the current expression of every declared
target that has been assigned so far (`assigned`, in `order`), the D18 block-local temporaries
(`temps`, keyed by `name` or `name[i]`), and the `for`-loop variables (`loopvars`)."""
mutable struct EventEnv
    assigned::Dict{String,BGSim.Expr}
    order::Vector{String}
    temps::Dict{String,BGSim.Expr}
    loopvars::Dict{Symbol,BGSim.Expr}
end

EventEnv() = EventEnv(Dict{String,BGSim.Expr}(), String[], Dict{String,BGSim.Expr}(),
    Dict{Symbol,BGSim.Expr}())

_copy_env(env::EventEnv) = EventEnv(
    copy(env.assigned), copy(env.order), copy(env.temps), copy(env.loopvars)
)

function _set_assigned!(env::EventEnv, id::String, value::BGSim.Expr)
    haskey(env.assigned, id) || push!(env.order, id)
    env.assigned[id] = value
    return nothing
end

# A QCtx whose locals are the D18 temporaries and `for` loop variables of this body, so the
# existing `_qualify` resolves them instead of reporting E003 (they are not block
# declarations). Declared signals stay in the block state and are substituted afterwards.
function _event_qctx(b::Builder, st::BlockState, env::EventEnv)
    locals = Dict{Symbol,QValue}()
    for (key, value) in env.temps
        occursin('[', key) && continue
        locals[Symbol(key)] = QValue((), BGSim.Expr[value])
    end
    for (name, value) in env.loopvars
        locals[name] = QValue((), BGSim.Expr[value])
    end
    return QCtx(b, st, locals)
end

# ---------------------------------------------------------------------------------------
# Substitution of earlier assignments into a later expression
# ---------------------------------------------------------------------------------------

"""    _subst_event(e, env) -> Expr

Replace every reference to a target assigned earlier in this body (and every D18 temporary
or loop variable) by its current expression. Untouched names stay in the AST and the
lowering wraps them in `Pre(...)`."""
function _subst_event(e::BGSim.Name, env::EventEnv)
    key = String(e.name)
    haskey(env.assigned, key) && return env.assigned[key]
    haskey(env.temps, key) && return env.temps[key]
    haskey(env.loopvars, e.name) && return env.loopvars[e.name]
    return e
end

function _subst_event(e::BGSim.Field, env::EventEnv)
    key = Flat.flat_id(e)
    haskey(env.assigned, key) && return env.assigned[key]
    return e
end

function _subst_event(e::BGSim.Index, env::EventEnv)
    key = _event_index_key(e)
    if key !== nothing
        haskey(env.assigned, key) && return env.assigned[key]
        haskey(env.temps, key) && return env.temps[key]
    end
    return BGSim.Index(
        _subst_event(e.base, env), BGSim.Expr[_subst_event(i, env) for i in e.indices],
        e.range,
    )
end

_subst_event(e::BGSim.Lit, ::EventEnv) = e

function _subst_event(e::BGSim.BinOp, env::EventEnv)
    return BGSim.BinOp(e.op, _subst_event(e.lhs, env), _subst_event(e.rhs, env), e.range)
end

function _subst_event(e::BGSim.UnOp, env::EventEnv)
    return BGSim.UnOp(e.op, _subst_event(e.operand, env), e.range)
end

function _subst_event(e::BGSim.Call, env::EventEnv)
    return BGSim.Call(
        e.fn, BGSim.Expr[_subst_event(a, env) for a in e.args], e.range
    )
end

function _subst_event(e::BGSim.IfElse, env::EventEnv)
    return BGSim.IfElse(
        _subst_event(e.cond, env), _subst_event(e.then, env),
        _subst_event(e.otherwise, env), e.range,
    )
end

function _subst_event(e::BGSim.Comparison, env::EventEnv)
    return BGSim.Comparison(
        e.op, _subst_event(e.lhs, env), _subst_event(e.rhs, env), e.range
    )
end

function _subst_event(e::BGSim.BoolOp, env::EventEnv)
    return BGSim.BoolOp(e.op, BGSim.Expr[_subst_event(a, env) for a in e.operands], e.range)
end

function _subst_event(e::BGSim.VectorLit, env::EventEnv)
    return BGSim.VectorLit(BGSim.Expr[_subst_event(a, env) for a in e.elements], e.range)
end

function _subst_event(e::BGSim.MatrixLit, env::EventEnv)
    return BGSim.MatrixLit(
        [BGSim.Expr[_subst_event(a, env) for a in row] for row in e.rows], e.range
    )
end

_subst_event(e, ::EventEnv) = e

# `name[i]` / `name[i,j]` as a string, for temporaries and indexed targets.
function _event_index_key(e::BGSim.Index)
    if e.base isa BGSim.Name
        indices = Int[]
        for i in e.indices
            i isa BGSim.Lit && i.value isa Integer || return nothing
            push!(indices, Int(i.value))
        end
        return String(e.base.name) * "[" * join(indices, ",") * "]"
    end
    return nothing
end

# Substitute a whole QValue.
_subst_qvalue(q::QValue, env::EventEnv) =
    QValue(q.shape, BGSim.Expr[_subst_event(e, env) for e in q.elems])

# ---------------------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------------------

# Qualify the target without applying event temporaries: an assignment target always names
# the declared variable, never the value assigned earlier in the body.
function _qualify_target(q::QCtx, st::BlockState, target::BGSim.Expr)
    plain = QCtx(q.b, st, Dict{Symbol,QValue}())
    if target isa BGSim.Name
        haskey(st.ids, target.name) || return nothing
        shape = st.shapes[target.name]
        ids = st.ids[target.name]
        r = BGSim.expr_range(target)
        return QValue(shape, BGSim.Expr[BGSim.Name(Symbol(id), r) for id in ids])
    elseif target isa BGSim.Index
        value = _qualify(plain, target)
        return value
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Statement walker
# ---------------------------------------------------------------------------------------

function _walk_event_body!(env::EventEnv, b::Builder, st::BlockState, body)
    ok = true
    for stmt in body
        ok &= _walk_event_stmt!(env, b, st, stmt)
    end
    return ok
end

function _walk_event_stmt!(env::EventEnv, b::Builder, st::BlockState, stmt)
    if stmt isa BGSim.Assign
        return _event_assign!(env, b, st, stmt.target, stmt.value, stmt.op, stmt.range)
    elseif stmt isa BGSim.CallStatement
        call = stmt.call
        if call.fn.name === :reinit && length(call.args) == 2
            return _event_assign!(
                env, b, st, call.args[1], call.args[2], :assign, stmt.range
            )
        end
        _report!(
            b, st;
            code = "E001",
            message = "`$(call.fn.name)` is not an event statement",
            range = stmt.range,
            scope = "@events",
            hint = "use `reinit(x, value)` or an assignment",
        )
        return false
    elseif stmt isa BGSim.IfStatement
        return _event_if!(env, b, st, stmt)
    elseif stmt isa BGSim.ForStatement
        return _event_for!(env, b, st, stmt)
    end
    return true
end

function _event_assign!(
    env::EventEnv,
    b::Builder,
    st::BlockState,
    target,
    value,
    op::Symbol,
    range,
)
    q = _event_qctx(b, st, env)
    rhs = _qualify(q, value)
    rhs === nothing && return false
    rhs = _subst_qvalue(rhs, env)

    # Resolve the target. A declared variable/output is an event action; an undeclared name
    # is a D18 temporary, which only exists inside this body.
    if target isa BGSim.Name && !haskey(st.decls, target.name)
        key = String(target.name)
        if isempty(rhs.shape)
            env.temps[key] = rhs.elems[1]
        else
            for (k, e) in enumerate(rhs.elems)
                env.temps[key * "[" * string(k) * "]"] = e
            end
        end
        return true
    elseif target isa BGSim.Index && target.base isa BGSim.Name &&
           !haskey(st.decls, target.base.name)
        key = _event_index_key(target)
        key === nothing && return false
        old = get(env.temps, key, nothing)
        env.temps[key] = old === nothing ? rhs.elems[1] :
                         _apply_assign(op, old, rhs.elems[1], range)
        return true
    end

    tq = _qualify_target(q, st, target)
    if tq === nothing
        _report!(
            b, st;
            code = "E003",
            message = "`$(sprint(show, target))` is not an assignable variable",
            range = range,
            scope = "@events",
            hint = "assign a @variables or @outputs value, or a new temporary (D18)",
        )
        return false
    end
    # Broadcast a scalar value over an array target, and a matching value element-wise.
    values = if length(tq.elems) == length(rhs.elems)
        rhs.elems
    elseif isempty(rhs.shape)
        BGSim.Expr[rhs.elems[1] for _ in tq.elems]
    elseif length(rhs.elems) == 1
        BGSim.Expr[rhs.elems[1] for _ in tq.elems]
    else
        _report!(
            b, st;
            code = "E004",
            message = "cannot assign $(length(rhs.elems)) values to $(length(tq.elems)) targets",
            range = range,
            scope = "@events",
        )
        return false
    end
    for (k, tv) in enumerate(tq.elems)
        id = Flat.flat_id(tv)
        old = get(env.assigned, id, tv)
        new = _apply_assign(op, old, values[k], range)
        _set_assigned!(env, id, new)
    end
    return true
end

function _apply_assign(op::Symbol, old, value, range)
    op === :assign && return value
    op === :+ && return BGSim.BinOp(:+, old, value, range)
    op === :- && return BGSim.BinOp(:-, old, value, range)
    op === :* && return BGSim.BinOp(:*, old, value, range)
    op === :/ && return BGSim.BinOp(:/, old, value, range)
    return value
end

# `if`/`elseif`/`else` in an event body: every branch sees the same incoming environment;
# every target a branch writes is merged into one `ifelse` chain so the event affect stays a
# single expression per target.
function _event_if!(env::EventEnv, b::Builder, st::BlockState, stmt::BGSim.IfStatement)
    q = _event_qctx(b, st, env)
    branch_envs = EventEnv[]
    conds = Union{BGSim.Expr,Nothing}[]
    for branch in stmt.branches
        cond = nothing
        if branch.cond !== nothing
            c = _qualify(q, branch.cond)
            if c === nothing || !isempty(c.shape)
                _report!(
                    b, st;
                    code = "E004",
                    message = "the condition of an `if` must be a scalar",
                    range = BGSim.source_range(branch),
                    scope = "@events",
                )
                return false
            end
            cond = _subst_event(c.elems[1], env)
        end
        local_env = _copy_env(env)
        for sub in branch.body
            _walk_event_stmt!(local_env, b, st, sub) || return false
        end
        push!(branch_envs, local_env)
        push!(conds, cond)
    end

    keys = String[]
    for branch_env in branch_envs
        for key in branch_env.order
            key in keys || push!(keys, key)
        end
    end
    for key in keys
        current = get(env.assigned, key, nothing)
        current === nothing && (current = _name_for_id(st, key))
        current === nothing && continue
        for idx in length(branch_envs):-1:1
            value = get(branch_envs[idx].assigned, key, nothing)
            value === nothing && continue
            cond = conds[idx]
            current = cond === nothing ? value :
                      BGSim.IfElse(cond, value, current, stmt.range)
        end
        _set_assigned!(env, key, current)
    end

    temp_keys = String[]
    for branch_env in branch_envs
        for key in keys(branch_env.temps)
            key in temp_keys || push!(temp_keys, key)
        end
    end
    for key in temp_keys
        current = get(env.temps, key, nothing)
        current === nothing && continue
        for idx in length(branch_envs):-1:1
            value = get(branch_envs[idx].temps, key, nothing)
            value === nothing && continue
            cond = conds[idx]
            current = cond === nothing ? value :
                      BGSim.IfElse(cond, value, current, stmt.range)
        end
        env.temps[key] = current
    end
    return true
end

function _name_for_id(st::BlockState, id::String)
    for (name, ids) in st.ids
        id in ids && return BGSim.Name(Symbol(id), BGSim.SourceRange(0, 0, 0, 0))
    end
    return nothing
end

function _event_for!(env::EventEnv, b::Builder, st::BlockState, stmt::BGSim.ForStatement)
    lo = nothing
    hi = nothing
    step = 1
    ok_lo, lo = BGSim.try_eval_const(stmt.lo, st.consts)
    ok_hi, hi = BGSim.try_eval_const(stmt.hi, st.consts)
    if stmt.step !== nothing
        ok_step, s = BGSim.try_eval_const(stmt.step, st.consts)
        (ok_step && s isa Integer) || begin
            _report!(
                b, st;
                code = "E005",
                message = "the step of `for $(stmt.var)` must be a constant integer",
                range = stmt.range,
                scope = "@events",
            )
            return false
        end
        step = Int(s)
    end
    if !(ok_lo && ok_hi && lo isa Integer && hi isa Integer && step != 0)
        _report!(
            b, st;
            code = "E005",
            message = "the bounds of `for $(stmt.var)` must be constant integers",
            range = stmt.range,
            scope = "@events",
            hint = "use literals or `@constants`; a size depending on a parameter is not static",
        )
        return false
    end
    for i in collect(Int(lo):step:Int(hi))
        env.loopvars[stmt.var] = BGSim.Lit(i, stmt.range)
        ok = _walk_event_body!(env, b, st, stmt.body)
        delete!(env.loopvars, stmt.var)
        ok || return false
    end
    return true
end

# ---------------------------------------------------------------------------------------
# Collecting the events of a flattened model
# ---------------------------------------------------------------------------------------

"""    collect_events!(b) -> Vector{FlatEvent}

Qualify every `@events` entry of every instantiated block. Called once by `_flatten`, after
`instantiate!` has created the block states and before the `FlatModel` is frozen."""
function collect_events!(b::Builder)
    out = Any[]
    for st in b.states
        for ev in BGSim.events(st.pb)
            _collect_event!(out, b, st, ev)
        end
    end
    return out
end

function _collect_event!(out, b::Builder, st::BlockState, ev::BGSim.EventDecl)
    q = QCtx(b, st, Dict{Symbol,QValue}())
    zero = _qualify(q, BGSim.event_zero_crossing(ev))
    cond = _qualify(q, BGSim.event_condition(ev))
    if zero === nothing || cond === nothing
        return nothing
    end
    if !isempty(zero.shape) || !isempty(cond.shape)
        _report!(
            b, st;
            code = "E004",
            message = "an `@events` condition must be a scalar expression",
            range = BGSim.source_range(ev),
            scope = "@events",
        )
        return nothing
    end
    env = EventEnv()
    _walk_event_body!(env, b, st, ev.body) || return nothing
    actions = Pair{String,BGSim.Expr}[]
    for id in env.order
        push!(actions, id => env.assigned[id])
    end
    origin = Flat.Origin(; path = st.path, block = st.ref, node = st.node,
        range = BGSim.source_range(ev), kind = :block)
    push!(
        out,
        FlatEvent(cond.elems[1], zero.elems[1], actions, origin, BGSim.source_range(ev)),
    )
    return nothing
end

# ---------------------------------------------------------------------------------------
# Nonsmooth switching conditions
# ---------------------------------------------------------------------------------------

const NONSMOOTH_CALLS = Set{Symbol}([
    :ifelse, :abs, :sign, :min, :max, :clamp, :floor, :ceil, :round, :saturate, :deadzone,
])

# `a < b` / `a <= b` become `b - a`; `a > b` / `a >= b` become `a - b` (D19).
function _comparison_zero(c::BGSim.Comparison)
    r = c.range
    if c.op === :< || c.op === :<=
        return BGSim.BinOp(:-, c.rhs, c.lhs, r)
    elseif c.op === :> || c.op === :>=
        return BGSim.BinOp(:-, c.lhs, c.rhs, r)
    end
    return BGSim.BinOp(:-, c.lhs, c.rhs, r)
end

# The real expression(s) whose zero crossing is a switch of one nonsmooth call.
function _nonsmooth_zero_conditions(fn::Symbol, args::Vector{BGSim.Expr}, r::SourceRange)
    out = BGSim.Expr[]
    if fn === :ifelse
        length(args) == 3 || return out
        _collect_condition_zeros!(out, args[1])
    elseif fn === :abs || fn === :sign
        length(args) == 1 && push!(out, args[1])
    elseif fn === :min || fn === :max
        for i in 1:length(args), j in (i + 1):length(args)
            push!(out, BGSim.BinOp(:-, args[i], args[j], r))
        end
    elseif fn === :clamp || fn === :saturate || fn === :deadzone
        if length(args) == 2
            push!(out, BGSim.BinOp(:-, args[1], args[2], r))
            push!(out, BGSim.BinOp(:+, args[1], args[2], r))
        elseif length(args) == 3
            push!(out, BGSim.BinOp(:-, args[1], args[2], r))
            push!(out, BGSim.BinOp(:-, args[1], args[3], r))
        end
    elseif fn === :floor || fn === :ceil
        # Every integer is a kink; sin(pi*x) crosses zero at each one (the direction
        # alternates, which a condition-only callback does not care about).
        length(args) == 1 && push!(
            out,
            BGSim.Call(
                BGSim.Name(:sin, r),
                BGSim.Expr[BGSim.BinOp(:*, BGSim.Lit(Float64(pi), r), args[1], r)],
                r,
            ),
        )
    elseif fn === :round
        # round switches at half-integers.
        length(args) == 1 && push!(
            out,
            BGSim.Call(
                BGSim.Name(:sin, r),
                BGSim.Expr[BGSim.BinOp(
                    :*,
                    BGSim.Lit(Float64(pi), r),
                    BGSim.BinOp(:-, args[1], BGSim.Lit(0.5, r), r),
                    r,
                )],
                r,
            ),
        )
    end
    return out
end

function _collect_condition_zeros!(out::Vector{BGSim.Expr}, c::BGSim.Expr)
    if c isa BGSim.Comparison
        push!(out, _comparison_zero(c))
    elseif c isa BGSim.BoolOp
        for operand in c.operands
            _collect_condition_zeros!(out, operand)
        end
    elseif c isa BGSim.UnOp && c.op === Symbol("!")
        _collect_condition_zeros!(out, c.operand)
    end
    return out
end

function _walk_nonsmooth!(out::Vector{BGSim.Expr}, seen::Set{String}, e::BGSim.Expr)
    if e isa BGSim.Call
        fn = e.fn.name
        if fn in NONSMOOTH_CALLS
            for c in _nonsmooth_zero_conditions(fn, e.args, e.range)
                key = sprint(show, c)
                if !(key in seen)
                    push!(seen, key)
                    push!(out, c)
                end
            end
        end
        for a in e.args
            _walk_nonsmooth!(out, seen, a)
        end
    elseif e isa BGSim.IfElse
        # The zero crossings found above must also be deduplicated; collect them through the
        # same set by re-walking the condition as if it were an `ifelse` call.
        for c in _nonsmooth_zero_conditions(:ifelse, BGSim.Expr[e.cond, e.then, e.otherwise], e.range)
            key = sprint(show, c)
            if !(key in seen)
                push!(seen, key)
                push!(out, c)
            end
        end
        _walk_nonsmooth!(out, seen, e.then)
        _walk_nonsmooth!(out, seen, e.otherwise)
    elseif e isa BGSim.BinOp
        _walk_nonsmooth!(out, seen, e.lhs)
        _walk_nonsmooth!(out, seen, e.rhs)
    elseif e isa BGSim.UnOp
        _walk_nonsmooth!(out, seen, e.operand)
    elseif e isa BGSim.Comparison
        _walk_nonsmooth!(out, seen, e.lhs)
        _walk_nonsmooth!(out, seen, e.rhs)
    elseif e isa BGSim.BoolOp
        for a in e.operands
            _walk_nonsmooth!(out, seen, a)
        end
    elseif e isa BGSim.Index
        _walk_nonsmooth!(out, seen, e.base)
        for i in e.indices
            _walk_nonsmooth!(out, seen, i)
        end
    elseif e isa BGSim.VectorLit
        for a in e.elements
            _walk_nonsmooth!(out, seen, a)
        end
    elseif e isa BGSim.MatrixLit
        for row in e.rows, a in row
            _walk_nonsmooth!(out, seen, a)
        end
    elseif e isa BGSim.Field
        _walk_nonsmooth!(out, seen, e.base)
    end
    return out
end

"""    nonsmooth_conditions(flat) -> Vector{Expr}

The switching conditions of every continuous equation (plan 5.8), as real expressions whose
upward zero crossing is the switch. Duplicates are removed in first-seen order, so the
compile key and the callback order are deterministic."""
function nonsmooth_conditions(flat::Flat.FlatModel)
    out = BGSim.Expr[]
    seen = Set{String}()
    for eq in flat.equations
        _walk_nonsmooth!(out, seen, eq.lhs)
        _walk_nonsmooth!(out, seen, eq.rhs)
    end
    return out
end

# ---------------------------------------------------------------------------------------
# Lowering the collected events to SymbolicContinuousCallback
# ---------------------------------------------------------------------------------------

"""
    event_callbacks(flat, ctx) -> Vector{Any}

Turn every [`FlatEvent`](@ref) into one `SymbolicContinuousCallback` whose affect is the
final assignment map (plan D19, section 5.8). The event fires on the **rising** edge only
(`affect`, not `affect_neg`). Every state read but not written earlier in the body is wrapped
in `Pre(...)`; the `Pair` form is not used because it would wrap an already substituted
right-hand side as well.
"""
function event_callbacks(flat::Flat.FlatModel, ctx)
    out = Any[]
    for ev in flat.events
        ev isa FlatEvent || continue
        ctx.origin = ev.origin
        affects = BGSim.Symbolics.Equation[]
        params_written = Any[]
        try
            ctx.event_values = nothing
            condition = BGSim.lower_expression(ev.zero_crossing, ctx)
            ctx.event_values = Dict{String,Any}()
            for (id, expr) in ev.actions
                value = BGSim.lower_expression(expr, ctx)
                target = get(ctx.vars, id, nothing)
                if target === nothing
                    target = get(ctx.params, id, nothing)
                    target === nothing && throw(BGSim.LowerError(
                        "the `@events` target `$id` has no lowered variable", ev.origin
                    ))
                    push!(params_written, target)
                end
                push!(affects, target ~ value)
                ctx.event_values[id] = value
            end
            kwargs = (;)
            if !isempty(params_written)
                kwargs = merge(kwargs, (; discrete_parameters = params_written))
            end
            # MTK 11.45 takes the positive-edge affect as the second **positional** argument
            # and defaults `affect_neg = affect`; pass `affect_neg = nothing` so only the
            # upward crossing (D19) fires. The `affect` keyword is silently ignored here.
            cb = if isempty(affects)
                BGSim.ModelingToolkit.SymbolicContinuousCallback(condition ~ 0; kwargs...)
            else
                BGSim.ModelingToolkit.SymbolicContinuousCallback(
                    condition ~ 0, affects; affect_neg = nothing, kwargs...
                )
            end
            push!(out, cb)
        finally
            ctx.event_values = nothing
        end
    end
    return out
end
