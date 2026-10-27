# The discrete scheduler's compile half (plan section 5.9, decisions D3/D4/D18, E104/E105).
#
# Two jobs live here:
#
#   1. Collecting the `@discrete` scopes of every instantiated block into
#      [`DiscretePartition`](@ref) objects on the flat model (`FlatModel.discrete`). A
#      partition's body is qualified against the same `QCtx`/`QValue` machinery as the
#      continuous equations, so every name in it is a fully qualified scalar signal id and
#      `for` loops/temporaries are already unrolled or allocated. Held discrete outputs
#      (variables/outputs assigned in `@discrete`) stop being continuous unknowns: they move
#      from `FlatModel.variables` to `FlatModel.parameters` with `attrs[:kind] === :discrete`
#      (D4: they are runtime MTK parameters, never folded).
#
#   2. Turning a partition into a Julia expression for its generated step function
#      `step!(dstate, inputs, params, t)` ([`step_expression`](@ref)). The expression is
#      built from our validated AST, never from user text: the only names it contains are
#      array indices, literal numbers, arithmetic operators and a small set of helper
#      functions supplied by the caller. `src/sim/scheduler.jl` compiles it with
#      `RuntimeGeneratedFunctions`, so this file never calls `eval` either.
#
# Scheduling rules:
#
#   * `Ts` and `offset` become integer nanoseconds. A period or offset that is not a whole
#     number of nanoseconds is E104 ("use a period that is a whole number of nanoseconds").
#     The base tick is the gcd of all periods; a period that is not a multiple of it is E104.
#   * The clock is folded **per instance**: `Ts = sample_period` with an instance override of
#     that structural constant (D13) gives that instance its own period and its own E104
#     check, while another instance of the same block keeps the source default.
#   * An assignment target may be an element of a declared array (`v[k] = ...`), indexed by a
#     `for` loop variable or a literal; the loop is unrolled, so the target is a flat scalar
#     id like any other held value.
#   * Partitions are ordered topologically over signal connections and over reads of held
#     values. A read inside `previous(x)` does not create a dependency (it sees the value
#     from before this tick), which is exactly how `previous` breaks a cycle. A cycle that
#     `previous` does not break is E105, naming the partitions in the cycle.
#   * `hold(x)` is an explicit sample of a continuous signal: it reads the value at the tick
#     instant like any other continuous read, and creates the same dependency.
#
# Operation order and bit-exactness: the generated function executes the statements in source
# order, and each statement is `target = target OP rhs` for a compound assignment. A binary
# expression is emitted as the AST's own tree, so `i + Ts * e` is `i + (Ts * e)` and
# `Kp * e + Ki * i` is `(Kp * e) + (Ki * i)`; no reassociation or FMA fusion is introduced.
# That is the order `test/test_discrete.jl`'s hand computation uses, so Float64 `==` holds.

# ---------------------------------------------------------------------------------------
# Statement IR of one partition
# ---------------------------------------------------------------------------------------

"""    DiscreteAssign(kind, target, value, op, range)

One scalar assignment in a discrete body. `kind` is `:held` (a declared `@variables`/`@outputs`
value, held in `dstate`) or `:temp` (a D18 block-local temporary). `target` is the held signal
id or the temporary's local-slot symbol; `value` is the qualified scalar AST; `op` is
`:assign` or a compound operator (`:+`, `:-`, `:*`, `:/`)."""
struct DiscreteAssign
    kind::Symbol
    target::Any
    value::BGSim.Expr
    op::Symbol
    range::SourceRange
end

function Base.show(io::IO, a::DiscreteAssign)
    print(io, a.kind === :held ? a.target : string(a.target), ' ', a.op === :assign ? '=' : string(a.op, '='), ' ')
    show(io, a.value)
    return nothing
end

"""    DiscreteIf(branches, range)

One `if`/`elseif`/`else` statement. Each branch is `(condition, statements)` with `condition
=== nothing` for `else`; conditions are qualified scalar ASTs."""
struct DiscreteIf
    branches::Vector{Tuple{Union{Nothing,BGSim.Expr},Vector{Any}}}
    range::SourceRange
end

function Base.show(io::IO, s::DiscreteIf)
    print(io, "if ")
    for (i, (cond, body)) in enumerate(s.branches)
        i > 1 && print(io, " elseif ")
        cond === nothing ? print(io, "else") : show(io, cond)
        print(io, " {")
        for stmt in body
            show(io, stmt)
            print(io, "; ")
        end
        print(io, "}")
    end
    return nothing
end

"""    DiscretePartition

One `@discrete Ts = ...` scope of one instance, ready for scheduling and code generation.

* `period`/`offset` are the folded Float64 clock values (`Ts` inside the body is `period`);
  `period_ns`/`offset_ns` are the exact integer-nanosecond clock.
* `statements` is the [`DiscreteAssign`](@ref)/[`DiscreteIf`](@ref) IR.
* `reads` are every signal id read outside `previous(x)`, `previous_reads` those read inside
  it (in first-use order, `t` omitted).
* `writes` are the held ids this partition writes. `held_reads`, `param_reads` and
  `input_reads` classify `reads` after the held values have been moved to parameters.
* `temp_slots` are the local variables of the generated function (D18).
"""
struct DiscretePartition
    label::String
    path::String
    node::String
    ref::String
    period::Float64
    offset::Float64
    period_ns::Int64
    offset_ns::Int64
    statements::Vector{Any}
    reads::Vector{String}
    previous_reads::Vector{String}
    writes::Vector{String}
    temp_slots::Vector{Symbol}
    held_reads::Vector{String}
    param_reads::Vector{String}
    input_reads::Vector{String}
    origin::Flat.Origin
    range::SourceRange
end

function Base.show(io::IO, p::DiscretePartition)
    print(io, "discrete(", p.label, ", Ts=", p.period_ns, "ns, offset=", p.offset_ns, "ns; ")
    for stmt in p.statements
        show(io, stmt)
        print(io, "; ")
    end
    print(io, ")")
    return nothing
end

# ---------------------------------------------------------------------------------------
# Walking a discrete body
# ---------------------------------------------------------------------------------------

"""    DiscreteWalk

The mutable state of one partition while its body is walked: the statement list being built,
the read/write sets, the temporary slots and the `QCtx` locals (D18 temporaries and `for`
loop variables)."""
mutable struct DiscreteWalk
    b::Builder
    st::BlockState
    label::String
    index::Int
    stmts::Vector{Any}
    reads::Vector{String}
    previous_reads::Vector{String}
    writes::Vector{String}
    temp_slots::Vector{Symbol}
    temp_names::Set{Symbol}
    locals::Dict{Symbol,QValue}
end

_push_unique!(v::Vector{String}, x::String) = (x in v || push!(v, x); nothing)
_push_unique!(v::Vector{Symbol}, x::Symbol) = (x in v || push!(v, x); nothing)
_push_unique!(v::Vector{Int}, x::Int) = (x in v || push!(v, x); nothing)
_push_unique!(s::Set{Symbol}, x::Symbol) = (push!(s, x); nothing)

# The deterministic local-slot symbol of a D18 temporary element. It must not depend on a
# global counter: `compile_key` hashes the partition's `show`, and a fresh gensym per compile
# would change the structural key between runs of the same model.
_temp_slot(w::DiscreteWalk, name::Symbol, k::Integer) =
    Symbol("__d", w.index, "_", name, "_", k)

# Qualify a scalar/array expression in the current local environment.
function _disc_qualify(w::DiscreteWalk, e)
    return _qualify(QCtx(w.b, w.st, w.locals), e)
end

function _disc_report!(w::DiscreteWalk; code, message, range = nothing, hint = nothing)
    _report!(w.b, w.st; code = code, message = message, range = range, hint = hint,
        scope = "@discrete")
    return nothing
end

# ---------------------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------------------

_pervious_call(e) = e isa BGSim.Call && e.fn.name === :previous

function _disc_reads!(w::DiscreteWalk, e::BGSim.Expr, in_previous::Bool)
    if e isa BGSim.Name
        key = String(e.name)
        key == "t" && return nothing
        e.name in w.temp_names && return nothing
        key == "Ts" && return nothing
        _push_unique!(in_previous ? w.previous_reads : w.reads, key)
    elseif e isa BGSim.Field
        _push_unique!(in_previous ? w.previous_reads : w.reads, Flat.flat_id(e))
    elseif e isa BGSim.Call
        inside = in_previous || e.fn.name === :previous
        for a in e.args
            _disc_reads!(w, a, inside)
        end
    elseif e isa BGSim.BinOp
        _disc_reads!(w, e.lhs, in_previous)
        _disc_reads!(w, e.rhs, in_previous)
    elseif e isa BGSim.UnOp
        _disc_reads!(w, e.operand, in_previous)
    elseif e isa BGSim.IfElse
        _disc_reads!(w, e.cond, in_previous)
        _disc_reads!(w, e.then, in_previous)
        _disc_reads!(w, e.otherwise, in_previous)
    elseif e isa BGSim.Comparison
        _disc_reads!(w, e.lhs, in_previous)
        _disc_reads!(w, e.rhs, in_previous)
    elseif e isa BGSim.BoolOp
        for a in e.operands
            _disc_reads!(w, a, in_previous)
        end
    elseif e isa BGSim.Index
        _disc_reads!(w, e.base, in_previous)
        for i in e.indices
            _disc_reads!(w, i, in_previous)
        end
    elseif e isa BGSim.VectorLit
        for a in e.elements
            _disc_reads!(w, a, in_previous)
        end
    elseif e isa BGSim.MatrixLit
        for row in e.rows, a in row
            _disc_reads!(w, a, in_previous)
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------------------

# `values` is one scalar expression per target element, `op` the (possibly compound) operator.
function _emit_scalar_assign!(
    w::DiscreteWalk,
    kind::Symbol,
    target,
    value::BGSim.Expr,
    op::Symbol,
    range,
)
    kind === :held && target isa String && _push_unique!(w.writes, target)
    push!(w.stmts, DiscreteAssign(kind, target, value, op, range))
    return nothing
end

# Broadcast `rhs` over the target's scalar elements (scalar value → every element, matching
# length → element-wise), as an event affect does.
function _broadcast_values(
    w::DiscreteWalk,
    kind::Symbol,
    target::Vector,
    rhs::QValue,
    op::Symbol,
    range,
)
    values = if length(target) == length(rhs.elems)
        rhs.elems
    elseif isempty(rhs.shape) || length(rhs.elems) == 1
        BGSim.Expr[rhs.elems[1] for _ in target]
    else
        _disc_report!(
            w; code = "E004",
            message = "cannot assign $(length(rhs.elems)) values to $(length(target)) targets",
            range = range,
        )
        return false
    end
    for (k, tv) in enumerate(target)
        _emit_scalar_assign!(w, kind, tv, values[k], op, range)
    end
    return true
end

_disc_name(sym::Symbol, range::SourceRange) = BGSim.Name(sym, range)

function _assign_temp!(w::DiscreteWalk, name::Symbol, rhs::QValue, op::Symbol, range)
    if op !== :assign && !haskey(w.locals, name)
        _disc_report!(
            w; code = "E003", message = "`$name` is used but not declared",
            hint = "write `$name = ...` first to create a temporary (D18)", range = range,
        )
        return false
    end
    old = get(w.locals, name, nothing)
    if old !== nothing && op === :assign && old.shape != rhs.shape
        _disc_report!(
            w; code = "E004",
            message = "temporary `$name` was $(isempty(old.shape) ? "a scalar" : "an array") " *
                      "and cannot be reassigned to a different size",
            range = range,
        )
        return false
    end
    shape = old === nothing || op === :assign ? rhs.shape : old.shape
    # A compound assignment keeps the target's size (`v += scalar` broadcasts over the vector).
    count = old === nothing ? length(rhs.elems) : length(old.elems)
    slots = Symbol[_temp_slot(w, name, k) for k in 1:max(1, count)]
    for slot in slots
        _push_unique!(w.temp_slots, slot)
        _push_unique!(w.temp_names, slot)
    end
    w.locals[name] = QValue(shape, BGSim.Expr[_disc_name(slot, range) for slot in slots])
    return _broadcast_values(w, :temp, slots, rhs, op, range)
end

function _assign_temp_element!(
    w::DiscreteWalk,
    name::Symbol,
    index::BGSim.Expr,
    rhs::QValue,
    op::Symbol,
    range,
)
    base = get(w.locals, name, nothing)
    if base === nothing
        _disc_report!(
            w; code = "E003", message = "`$name` is used but not declared",
            hint = "write `$name = ...` first to create a temporary (D18)", range = range,
        )
        return false
    end
    k = _disc_element_index(w, base, index)
    k === nothing && return false
    slot = base.elems[k]
    slot isa BGSim.Name || return false
    return _broadcast_values(w, :temp, Symbol[slot.name], rhs, op, range)
end

function _disc_element_index(w::DiscreteWalk, base::QValue, index)
    indices = Int[]
    for idx in index.indices
        v = _disc_qualify(w, idx)
        v === nothing && return nothing
        isempty(v.shape) || return nothing
        ok, value = BGSim.try_eval_const(v.elems[1], w.st.consts)
        value isa Integer || return nothing
        push!(indices, Int(value))
    end
    length(indices) == length(base.shape) || begin
        _disc_report!(
            w; code = "E005",
            message = "an array of size $(base.shape) takes $(length(base.shape)) indices",
            range = BGSim.expr_range(index),
        )
        return nothing
    end
    for (d, i) in enumerate(indices)
        (1 <= i <= base.shape[d]) || begin
            _disc_report!(
                w; code = "E005", message = "index $i is out of range for size $(base.shape)",
                range = BGSim.expr_range(index),
            )
            return nothing
        end
    end
    return length(indices) == 1 ? indices[1] :
           (indices[1] - 1) * base.shape[2] + indices[2]
end

# The assignment target of a declared array element, qualified with the discrete walk's
# locals so a `for` loop variable can index it (`v[k] = u`, plan 4.3's unrolled loops). The
# discrete `_assign_held!` needs the target's element ids only, so unlike an `@events` target
# this never consults earlier writes: a declared signal is always named by its flat ids. A
# local is never a declared name (D18 temporaries exist only for undeclared names), so
# resolving `base` through `st.ids` is unambiguous.
function _qualify_discrete_target(w::DiscreteWalk, target)
    return _qualify(QCtx(w.b, w.st, w.locals), target)
end

# An assignment target created from `_qualify_target` (declared variable/output element).
function _assign_held!(w::DiscreteWalk, target::QValue, rhs::QValue, op::Symbol, range)
    ids = String[]
    for e in target.elems
        e isa BGSim.Name || begin
            _disc_report!(w; code = "E004", message = "this target is not assignable",
                range = range)
            return false
        end
        push!(ids, String(e.name))
    end
    return _broadcast_values(w, :held, ids, rhs, op, range)
end

function _disc_assign!(
    w::DiscreteWalk,
    stmt::BGSim.Assign,
)
    target = BGSim.assign_target(stmt)
    value = BGSim.assign_value(stmt)
    op = BGSim.assign_op(stmt)
    range = BGSim.source_range(stmt)
    rhs = _disc_qualify(w, value)
    rhs === nothing && return false
    for e in rhs.elems
        _disc_reads!(w, e, false)
    end

    if target isa BGSim.Name
        name = target.name
        d = get(w.st.decls, name, nothing)
        if d === nothing
            return _assign_temp!(w, name, rhs, op, range)
        end
        scope = BGSim.decl_scope(d)
        if !(scope in (:variables, :outputs))
            article = scope === :inputs ? "an input" :
                      scope === :parameters ? "a parameter" :
                      scope === :constants ? "a constant" :
                      scope === :ports ? "a port" :
                      "declared in " * BGSim.scope_string(scope)
            _disc_report!(
                w; code = "E004",
                message = "`$name` is $article and cannot be assigned",
                range = range,
            )
            return false
        end
        ids = String[String(id) for id in w.st.ids[name]]
        return _broadcast_values(w, :held, ids, rhs, op, range)
    elseif target isa BGSim.Index
        base = target.base
        if base isa BGSim.Name && !haskey(w.st.decls, base.name)
            return _assign_temp_element!(w, base.name, target, rhs, op, range)
        end
        tq = _qualify_discrete_target(w, target)
        tq === nothing && return false
        return _assign_held!(w, tq, rhs, op, range)
    end
    _disc_report!(
        w; code = "E001", message = "the left side of an assignment must be a name or an index",
        range = range,
    )
    return false
end

# ---------------------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------------------

function _disc_body!(w::DiscreteWalk, body::Vector{Any})::Bool
    ok = true
    for stmt in body
        ok &= _disc_stmt!(w, stmt)
    end
    return ok
end

function _disc_stmt!(w::DiscreteWalk, stmt)::Bool
    if stmt isa BGSim.Assign
        return _disc_assign!(w, stmt)
    elseif stmt isa BGSim.IfStatement
        return _disc_if!(w, stmt)
    elseif stmt isa BGSim.ForStatement
        return _disc_for!(w, stmt)
    elseif stmt isa BGSim.CallStatement
        call = BGSim.stmt_call(stmt)
        _disc_report!(
            w; code = "E001",
            message = "`$(call.fn.name)` is not a discrete statement",
            hint = "use an assignment; `reinit` is only available in @events",
            range = BGSim.source_range(stmt),
        )
        return false
    end
    return true
end

function _disc_if!(w::DiscreteWalk, stmt::BGSim.IfStatement)::Bool
    branches = Tuple{Union{Nothing,BGSim.Expr},Vector{Any}}[]
    branch_envs = Dict{Symbol,QValue}[]
    for branch in stmt.branches
        cond = nothing
        if branch.cond !== nothing
            c = _disc_qualify(w, branch.cond)
            c === nothing && return false
            for e in c.elems
                _disc_reads!(w, e, false)
            end
            if !isempty(c.shape)
                _disc_report!(
                    w; code = "E004", message = "the condition of an `if` must be a scalar",
                    range = BGSim.source_range(branch),
                )
                return false
            end
            cond = c.elems[1]
        end
        saved_locals = copy(w.locals)
        saved_stmts = w.stmts
        w.stmts = Any[]
        ok = true
        for sub in branch.body
            ok &= _disc_stmt!(w, sub)
            ok || break
        end
        body = w.stmts
        w.stmts = saved_stmts
        ok || return false
        push!(branches, (cond, body))
        push!(branch_envs, copy(w.locals))
        w.locals = saved_locals
    end
    # A temporary created inside a branch is visible after the `if` (every slot starts at
    # 0.0, so a skipped branch keeps 0.0). The branches must agree on its size; a temporary
    # that existed before the `if` keeps its slots, because every branch writes the same ones.
    for env in branch_envs, (name, q) in env
        haskey(w.locals, name) && continue
        for other in branch_envs
            other_q = get(other, name, nothing)
            other_q === nothing && continue
            other_q.shape == q.shape || begin
                _disc_report!(
                    w; code = "E004",
                    message = "temporary `$name` has different sizes in the branches of an `if`",
                    range = stmt.range,
                )
                return false
            end
        end
        w.locals[name] = q
    end
    push!(w.stmts, DiscreteIf(branches, stmt.range))
    return true
end

function _disc_for!(w::DiscreteWalk, stmt::BGSim.ForStatement)::Bool
    ok_lo, lo = BGSim.try_eval_const(stmt.lo, w.st.consts)
    ok_hi, hi = BGSim.try_eval_const(stmt.hi, w.st.consts)
    step = 1
    if stmt.step !== nothing
        ok_step, s = BGSim.try_eval_const(stmt.step, w.st.consts)
        (ok_step && s isa Integer && s != 0) || begin
            _disc_report!(
                w; code = "E005",
                message = "the step of `for $(stmt.var)` must be a constant integer",
                range = stmt.range,
            )
            return false
        end
        step = Int(s)
    end
    if !(ok_lo && ok_hi && lo isa Integer && hi isa Integer)
        _disc_report!(
            w; code = "E005",
            message = "the bounds of `for $(stmt.var)` must be constant integers",
            hint = "use literals or `@constants`; a size depending on a parameter is not static",
            range = stmt.range,
        )
        return false
    end
    for i in collect(Int(lo):step:Int(hi))
        w.locals[stmt.var] = _qscalar(BGSim.Lit(i, stmt.range))
        _disc_body!(w, stmt.body) || return false
        delete!(w.locals, stmt.var)
    end
    return true
end

# ---------------------------------------------------------------------------------------
# Collecting one partition
# ---------------------------------------------------------------------------------------

function _ns_clock(
    b::Builder,
    st::BlockState,
    ds,
    value::Float64,
    what::AbstractString;
    allow_zero::Bool = false,
)
    ns = value * 1.0e9
    rounded = round(ns)
    too_small = allow_zero ? rounded < 0 : rounded <= 0
    if abs(ns - rounded) > 1.0e-6 || too_small || rounded > 9.2e18
        push!(
            b.diagnostics,
            diag(
                "E104",
                "the @discrete $what $(value) s is not a whole number of nanoseconds";
                hint = "use a period that is a whole number of nanoseconds",
                path = st.path,
                block = st.ref,
                scope = "@discrete",
                source = SourceRef(BGSim.source_kind(st.ref), st.ref, BGSim.source_range(ds)),
                node = st.node,
            ),
        )
        return Int64(0)
    end
    return Int64(rounded)
end

"""    _instance_clock(st, expr, fallback) -> Float64

The clock value of one `@discrete` scope for this *instance*. The parser folds the period
once against the block's own `@constants` defaults, but an instance may override a constant
(D13: structural constants are per instance), and `_bind_constants!` has already applied that
override to `st.consts`. Re-folding the clock expression here therefore gives every instance
of the same block its own rate — `UnitDelay` at 1 ms next to `UnitDelay(constants =
{sample_period = 5e-3})` at 5 ms. `fallback` is the block-level folded value, used when the
expression does not fold here because a block-level E004 was already reported."""
function _instance_clock(st::BlockState, expr, fallback::Union{Float64,Nothing})
    ok, value = BGSim.try_eval_const(expr, st.consts)
    if ok && value isa Real && !(value isa Bool)
        return Float64(value)
    end
    return fallback
end

function _collect_partition!(b::Builder, st::BlockState, ds, k::Int, index::Int)
    period = _instance_clock(st, ds.period, BGSim.discrete_period(ds))
    period === nothing && return nothing
    offset = ds.offset === nothing ? 0.0 :
             something(_instance_clock(st, ds.offset, BGSim.discrete_offset(ds)), 0.0)
    period_ns = _ns_clock(b, st, ds, period, "period")
    # An invalid clock (E104) keeps its held values (so the model still balances and the
    # editor can show them) but is `period_ns == 0` and never scheduled.
    offset_ns = period_ns == 0 ? Int64(0) :
                _ns_clock(b, st, ds, offset, "offset"; allow_zero = true)

    label = st.path * " @discrete[" * string(k) * "]"
    w = DiscreteWalk(
        b, st, label, index, Any[], String[], String[], String[], Symbol[],
        Set{Symbol}(), Dict{Symbol,QValue}(),
    )
    # `Ts` is the folded Float64 period inside the body (plan 5.9), for *this instance* after
    # the constant override above. Making it a literal keeps the generated arithmetic
    # identical to what the source wrote, e.g. `Ts * e` with Ts = 0.001 exactly the literal
    # 0.001 (and 0.005 for an instance that overrode `sample_period`).
    w.locals[:Ts] = _qscalar(BGSim.Lit(period, BGSim.source_range(ds)))
    _disc_body!(w, ds.body)

    origin = Flat.Origin(; path = st.path, block = st.ref, node = st.node,
        range = BGSim.source_range(ds), kind = :block)
    return DiscretePartition(
        label, st.path, st.node, st.ref, period, offset, period_ns, offset_ns,
        w.stmts, w.reads, w.previous_reads, w.writes, w.temp_slots,
        String[], String[], String[], origin, BGSim.source_range(ds),
    )
end

# ---------------------------------------------------------------------------------------
# Held outputs become MTK parameters (D4)
# ---------------------------------------------------------------------------------------

function _held_default(v::Flat.FlatVar)
    v.type === :Bool && return false
    v.type === :Int && return 0
    return 0.0
end

"""
    collect_discrete!(b) -> Vector{DiscretePartition}

Qualify every `@discrete` scope of every instantiated block, move its held outputs from the
continuous unknown list to the parameter list (D4), check the clock (E104) and order the
partitions (E105). Called once by `_flatten`, after `instantiate!`.
"""
function collect_discrete!(b::Builder)
    raw = Any[]
    for st in b.states
        for (k, ds) in enumerate(BGSim.discrete_scopes(st.pb))
            part = _collect_partition!(b, st, ds, k, length(raw) + 1)
            part === nothing || push!(raw, part)
        end
    end
    isempty(raw) && return Any[]

    held = String[]
    for p in raw, id in p.writes
        _push_unique!(held, id)
    end
    _promote_held!(b, held)

    params = Set{String}(String(id) for id in keys(b.param_index))
    parts = Any[]
    for p in raw
        push!(parts, _classify_partition(p, held, params))
    end
    _check_base_tick!(b, parts)
    return _order_partitions!(b, parts)
end

function _classify_partition(p::DiscretePartition, held, params)
    held_reads = String[]
    param_reads = String[]
    input_reads = String[]
    for (i, id) in enumerate(p.reads)
        if id in held
            _push_unique!(held_reads, id)
        elseif id in params
            _push_unique!(param_reads, id)
        else
            _push_unique!(input_reads, id)
        end
    end
    return DiscretePartition(
        p.label, p.path, p.node, p.ref, p.period, p.offset, p.period_ns, p.offset_ns,
        p.statements, p.reads, p.previous_reads, p.writes, p.temp_slots,
        held_reads, param_reads, input_reads, p.origin, p.range,
    )
end

# Move every held discrete output from `b.vars` to `b.params`, with the declared start value as
# its initial parameter value. The signal list keeps the value (kind `"discrete"`), the balance
# count no longer sees it (it is not a continuous unknown) and the lowering reads it as a
# discrete MTK parameter.
function _promote_held!(b::Builder, held::Vector{String})
    isempty(held) && return nothing
    heldset = Set(held)
    removed = Dict{String,Flat.FlatVar}()
    kept = Flat.FlatVar[]
    for v in b.vars
        if v.id in heldset
            removed[v.id] = v
        else
            push!(kept, v)
        end
    end
    isempty(removed) && return nothing
    b.vars = kept
    empty!(b.var_index)
    for (i, v) in enumerate(b.vars)
        b.var_index[v.id] = i
    end
    for id in held
        v = get(removed, id, nothing)
        v === nothing && continue
        attrs = copy(v.attrs)
        attrs[:kind] = :discrete
        value = v.start === nothing ? _held_default(v) : v.start
        _add_param!(
            b,
            Flat.FlatParam(
                id, id, value, v.type, v.unit, attrs,
                Flat.Origin(; path = v.origin.path, block = v.origin.block,
                    range = v.origin.range, node = v.origin.node,
                    connection = v.origin.connection, kind = :discrete),
            ),
        )
    end
    for st in b.states
        for id in held
            v = get(removed, id, nothing)
            v === nothing && continue
            v.origin.path == st.path && (st.var_count -= 1)
        end
    end
    return nothing
end

"""    discrete_signal_namedtuple(p::FlatParam) -> NamedTuple

The plan 3.5 signal entry of a held discrete value: kind `"discrete"`."""
function discrete_signal_namedtuple(p::Flat.FlatParam)
    return (
        id = p.id,
        unit = p.unit === nothing ? nothing : BGSim.Units.unit_string(p.unit),
        kind = "discrete",
        path = p.origin.path,
        type = String(p.type),
    )
end

# ---------------------------------------------------------------------------------------
# E104: the base tick
# ---------------------------------------------------------------------------------------

function _check_base_tick!(b::Builder, parts::Vector)
    isempty(parts) && return nothing
    base = Int64(0)
    for p in parts
        p.period_ns > 0 || continue
        base = base == 0 ? p.period_ns : gcd(base, p.period_ns)
    end
    base == 0 && return nothing
    for p in parts
        p.period_ns > 0 || continue
        p.period_ns % base == 0 && continue
        push!(
            b.diagnostics,
            diag(
                "E104",
                "the @discrete period of `$(p.label)` is not a multiple of the base tick " *
                "$(base) ns";
                hint = "use a period that is a whole number of nanoseconds, and one that " *
                       "shares a common tick with the other discrete partitions",
                path = p.path,
                block = p.ref,
                scope = "@discrete",
                source = SourceRef(BGSim.source_kind(p.ref), p.ref, p.range),
                node = p.node,
            ),
        )
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# E105: the topological order
# ---------------------------------------------------------------------------------------

# The signal wiring map `from output id => to input ids` of every valid signal connection.
# A partition that reads `to` therefore depends on the partition that writes the held `from`.
function _signal_wiring(b::Builder)
    out = Dict{String,Vector{String}}()
    for raw in b.raw
        raw.conn.kind == :signal || continue
        raw.from.kind == :output || continue
        raw.to.kind == :input || continue
        from_st = get(b.state_by_path, raw.from.path, nothing)
        to_st = get(b.state_by_path, raw.to.path, nothing)
        (from_st === nothing || to_st === nothing) && continue
        from_ids = get(from_st.ids, something(raw.from.port, Symbol("")), String[])
        to_ids = get(to_st.ids, something(raw.to.port, Symbol("")), String[])
        length(from_ids) == length(to_ids) || continue
        for k in eachindex(from_ids)
            _push_unique!(get!(out, from_ids[k], String[]), to_ids[k])
        end
    end
    return out
end

function _partition_edges(b::Builder, parts::Vector)
    writers = Dict{String,Vector{Int}}()
    for (i, p) in enumerate(parts)
        for id in p.writes
            _push_unique!(get!(writers, id, Int[]), i)
        end
    end
    wiring = _signal_wiring(b)
    edges = [Set{Int}() for _ in parts]
    for (i, p) in enumerate(parts)
        # Direct reads of a held value.
        for id in p.held_reads
            for j in get(writers, id, Int[])
                j == i || push!(edges[j], i)
            end
        end
        # Reads of a continuous input whose signal source is a held value.
        for id in p.input_reads
            for (from_id, to_ids) in wiring
                from_id in to_ids && continue
                id in to_ids || continue
                for j in get(writers, from_id, Int[])
                    j == i || push!(edges[j], i)
                end
            end
        end
    end
    return edges
end

function _find_cycle(edges::Vector{Set{Int}}, order::Vector{Int})
    # DFS with colours over the partitions that Kahn could not order.
    state = zeros(Int8, length(edges))          # 0 = white, 1 = grey, 2 = black
    stack = Int[]
    cycle = Int[]

    function visit(i::Int)
        state[i] = 1
        push!(stack, i)
        for j in sort!(collect(edges[i]))
            if state[j] == 1
                at = findfirst(==(j), stack)
                cycle = at === nothing ? [i, j] : vcat(stack[at:end], [j])
                return true
            elseif state[j] == 0 && visit(j)
                return true
            end
        end
        pop!(stack)
        state[i] = 2
        return false
    end

    for i in order
        if state[i] == 0 && visit(i)
            return cycle
        end
    end
    return cycle
end

function _e105(b::Builder, parts::Vector, cycle::Vector{Int})
    names = [parts[i].label for i in cycle]
    message = "discrete partitions form a cycle: " * join(names, " -> ")
    first_part = parts[cycle[1]]
    related = [
        Related(parts[i].path, "is in the cycle: " * parts[i].label) for i in cycle[2:end]
    ]
    push!(
        b.diagnostics,
        diag(
            "E105",
            message;
            hint = "break the cycle with `previous(x)` (the value from before this tick), " *
                   "or remove one of the signal connections",
            path = first_part.path,
            block = first_part.ref,
            scope = "@discrete",
            source = SourceRef(BGSim.source_kind(first_part.ref), first_part.ref,
                first_part.range),
            node = first_part.node,
            related = related,
        ),
    )
    return nothing
end

function _order_partitions!(b::Builder, parts::Vector)
    isempty(parts) && return parts
    edges = _partition_edges(b, parts)
    indegree = zeros(Int, length(parts))
    for i in eachindex(edges), j in edges[i]
        indegree[j] += 1
    end
    # Kahn, always taking the lowest partition index so the order is deterministic.
    ready = sort([i for i in eachindex(parts) if indegree[i] == 0])
    ordered = Int[]
    while !isempty(ready)
        i = popfirst!(ready)
        push!(ordered, i)
        for j in sort!(collect(edges[i]))
            indegree[j] -= 1
            indegree[j] == 0 && push!(ready, j)
        end
        sort!(ready)
    end
    if length(ordered) != length(parts)
        remaining = [i for i in eachindex(parts) if !(i in ordered)]
        cycle = _find_cycle(edges, remaining)
        isempty(cycle) || _e105(b, parts, cycle)
        return parts
    end
    return Any[parts[i] for i in ordered]
end

# ---------------------------------------------------------------------------------------
# Code generation: a partition → `step!(dstate, inputs, params, t)` expression
# ---------------------------------------------------------------------------------------

# The generated function reads `dstate.values[i]`, `dstate.prev[i]`, `inputs.values[j]`,
# `inputs.prev[j]`, `params[k]`, `t` and `dstate.prev_t`. Every helper is emitted as a
# `GlobalRef` into the runtime module the caller passes, so `eval` never sees a user name.
_fld(obj::Symbol, field::Symbol) = Expr(:., obj, QuoteNode(field))

_held_ref(i::Int) = Expr(:ref, _fld(:dstate, :values), i)
_held_prev_ref(i::Int) = Expr(:ref, _fld(:dstate, :prev), i)
_input_ref(i::Int) = Expr(:ref, _fld(:inputs, :values), i)
_input_prev_ref(i::Int) = Expr(:ref, _fld(:inputs, :prev), i)
_param_ref(i::Int) = Expr(:ref, :params, i)

function _step_signal_ref(
    key::String,
    prev::Bool,
    held::Dict{String,Int},
    inputs::Dict{String,Int},
    params::Dict{String,Int},
)
    i = get(held, key, 0)
    i > 0 && return prev ? _held_prev_ref(i) : _held_ref(i)
    i = get(inputs, key, 0)
    i > 0 && return prev ? _input_prev_ref(i) : _input_ref(i)
    i = get(params, key, 0)
    i > 0 && return _param_ref(i)
    throw(LowerError("the discrete code reads `$key`, which has no lowered signal", nothing))
end

const _STEP_BASE_FUNCS = Set{Symbol}([
    :sin, :cos, :tan, :asin, :acos, :atan, :sinh, :cosh, :tanh, :exp, :log, :log10,
    :sqrt, :abs, :floor, :ceil, :hypot, :mod, :rem, :min, :max,
])

function _step_call(
    fn::Symbol,
    args::Vector{Any},
    helpers::Module,
    prev::Bool,
    held,
    inputs,
    params,
)
    if fn === :previous
        length(args) == 1 || throw(LowerError("`previous` takes one argument", nothing))
        return args[1]
    elseif fn === :hold
        length(args) == 1 || throw(LowerError("`hold` takes one argument", nothing))
        return args[1]
    elseif fn === :ifelse
        length(args) == 3 || throw(LowerError("`ifelse` takes three arguments", nothing))
        return Expr(:call, GlobalRef(helpers, :__ifelse), args...)
    elseif fn === :round
        length(args) == 1 || throw(LowerError("`round` takes one argument", nothing))
        return Expr(:call, GlobalRef(helpers, :__round), args[1])
    elseif fn === :clamp || fn === :saturate
        length(args) in (2, 3) ||
            throw(LowerError("`$fn` takes two or three arguments", nothing))
        return Expr(:call, GlobalRef(helpers, :__clamp), args...)
    elseif fn === :deadzone
        length(args) in (2, 3) ||
            throw(LowerError("`deadzone` takes two or three arguments", nothing))
        return Expr(:call, GlobalRef(helpers, :__deadzone), args...)
    elseif fn === :sign
        length(args) == 1 || throw(LowerError("`sign` takes one argument", nothing))
        return Expr(:call, GlobalRef(helpers, :__sign), args[1])
    elseif fn in _STEP_BASE_FUNCS
        return Expr(:call, GlobalRef(Base, fn), args...)
    elseif fn === :delay || fn === :interp1 || fn === :interp2 || fn === :noise_normal
        throw(LowerError(
            "`$fn` is an intrinsic that the discrete scheduler does not lower (J2.7b)", nothing
        ))
    end
    throw(LowerError("function `$fn` cannot be lowered in discrete code", nothing))
end

"""    _step_value(e, prev, held, inputs, params, temp_slots, helpers) -> Expr

Compile one scalar qualified AST node. `prev` is true inside `previous(x)`: held values then
come from `dstate.prev`, continuous reads from `inputs.prev` and `t` from `dstate.prev_t`."""
function _step_value(e, prev::Bool, held, inputs, params, temp_slots::Set{Symbol},
    helpers::Module)
    if e isa BGSim.Lit
        v = e.value
        v isa Bool && return v
        v isa Integer && return v
        v isa AbstractFloat && return Float64(v)
        throw(LowerError("literal $(repr(v)) cannot appear in discrete code", nothing))
    elseif e isa BGSim.Name
        key = String(e.name)
        key == "t" && return prev ? _fld(:dstate, :prev_t) : :t
        e.name in temp_slots && return e.name
        return _step_signal_ref(key, prev, held, inputs, params)
    elseif e isa BGSim.Field
        return _step_signal_ref(Flat.flat_id(e), prev, held, inputs, params)
    elseif e isa BGSim.BinOp
        lhs = _step_value(e.lhs, prev, held, inputs, params, temp_slots, helpers)
        rhs = _step_value(e.rhs, prev, held, inputs, params, temp_slots, helpers)
        return Expr(:call, e.op, lhs, rhs)
    elseif e isa BGSim.UnOp
        operand = _step_value(e.operand, prev, held, inputs, params, temp_slots, helpers)
        return e.op === Symbol("!") ?
               Expr(:call, GlobalRef(helpers, :__not), operand) :
               Expr(:call, :-, operand)
    elseif e isa BGSim.Comparison
        lhs = _step_value(e.lhs, prev, held, inputs, params, temp_slots, helpers)
        rhs = _step_value(e.rhs, prev, held, inputs, params, temp_slots, helpers)
        return Expr(:call, e.op, lhs, rhs)
    elseif e isa BGSim.BoolOp
        args = Any[
            _step_value(a, prev, held, inputs, params, temp_slots, helpers) for
            a in e.operands
        ]
        op = e.op === Symbol("&&") ? :&& : :||
        out = args[1]
        for a in args[2:end]
            out = Expr(op, out, a)
        end
        return out
    elseif e isa BGSim.IfElse
        cond = _step_value(e.cond, prev, held, inputs, params, temp_slots, helpers)
        then = _step_value(e.then, prev, held, inputs, params, temp_slots, helpers)
        otherwise = _step_value(e.otherwise, prev, held, inputs, params, temp_slots, helpers)
        return Expr(:call, GlobalRef(helpers, :__ifelse), cond, then, otherwise)
    elseif e isa BGSim.Call
        fn = e.fn.name
        if fn === :previous || fn === :hold
            inside = fn === :previous ? true : prev
            args = Any[
                _step_value(a, inside, held, inputs, params, temp_slots, helpers) for
                a in e.args
            ]
            return _step_call(fn, args, helpers, inside, held, inputs, params)
        end
        args = Any[
            _step_value(a, prev, held, inputs, params, temp_slots, helpers) for a in e.args
        ]
        return _step_call(fn, args, helpers, prev, held, inputs, params)
    elseif e isa BGSim.Index
        throw(LowerError(
            "an unresolved array index reached discrete code generation", nothing
        ))
    end
    throw(LowerError("expression `$(sprint(show, e))` cannot be lowered in discrete code",
        nothing))
end

function _step_statement(stmt, held, inputs, params, temp_slots, helpers)
    if stmt isa DiscreteAssign
        target = stmt.kind === :held ? _held_ref(held[stmt.target]) :
                 (stmt.target::Symbol)
        rhs = _step_value(stmt.value, false, held, inputs, params, temp_slots, helpers)
        value = stmt.op === :assign ? rhs : Expr(:call, stmt.op, target, rhs)
        return Expr(:(=), target, value)
    elseif stmt isa DiscreteIf
        # Build the elseif chain from the last branch (the `else`) upwards.
        otherwise = Expr(:block)
        for (cond, body) in reverse(collect(stmt.branches))
            block = Expr(:block,
                [_step_statement(s, held, inputs, params, temp_slots, helpers) for s in body]...)
            if cond === nothing
                otherwise = block
            else
                c = _step_value(cond, false, held, inputs, params, temp_slots, helpers)
                otherwise = Expr(:if, Expr(:call, GlobalRef(helpers, :__truthy), c),
                    block, otherwise)
            end
        end
        return otherwise
    end
    throw(LowerError("unknown discrete statement", nothing))
end

"""    step_expression(partition, held, inputs, params, helpers) -> Expr

Build the anonymous function `(dstate, inputs, params, t) -> ...` of one partition. `held`,
`inputs` and `params` map a signal id to its index in the shared runtime vectors; `helpers` is
the module holding the `__truthy`/`__ifelse`/... helpers (a `GlobalRef` is emitted, so no
user name can ever resolve through this module)."""
function step_expression(
    p::DiscretePartition,
    held::Dict{String,Int},
    inputs::Dict{String,Int},
    params::Dict{String,Int},
    helpers::Module,
)
    temp_set = Set{Symbol}(p.temp_slots)
    preamble = Any[Expr(:local, Expr(:(=), slot, 0.0)) for slot in p.temp_slots]
    body = Any[
        _step_statement(s, held, inputs, params, temp_set, helpers) for s in p.statements
    ]
    block = Expr(:block, preamble..., body..., :(return nothing))
    return Expr(:->, Expr(:tuple, :dstate, :inputs, :params, :t), block)
end

export DiscretePartition, DiscreteAssign, DiscreteIf, collect_discrete!, step_expression,
    discrete_signal_namedtuple
