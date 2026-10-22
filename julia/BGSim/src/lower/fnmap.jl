# Lowering of the front-end AST to Symbolics (plan section 5.8).
#
# `fnmap.jl` is the one place where a language function becomes a Symbolics expression. The
# whitelist in `src/syntax/whitelist.jl` decides *whether* a function is allowed; this file
# decides *what it means*. The flat model (`src/ir/flat.jl`) already contains only scalar
# expressions with fully qualified names, arrays unrolled, `for` loops expanded, `if`
# equations split, and `dot`/`norm`/`cross`/`transpose` turned into scalar arithmetic by the
# flattener. That is why every expression here is scalar.
#
# Rules that matter:
#
# * `ddt` becomes `D` (`ModelingToolkit.D_nounits`), never a string nor `eval`.
# * `int(x, x0)` is sugar for a new state with `D(s) ~ x` and the start value `x0` (the spec
#   calls it "sugar for a new state with ddt"). The state is named deterministically from the
#   instance path and a counter, and its start expression is kept in the AST so a
#   parameter-only re-run can evaluate it with the current parameter values.
# * Nonsmooth functions are rewritten into `ifelse` forms. Symbolics could evaluate `abs`,
#   `min`, `max` and `clamp` itself, but rewriting makes every switching condition explicit,
#   which is what the J2.3 event collector needs, and avoids relying on derivatives of
#   non-differentiable heads.
# * `&&`, `||` and `!` are lowered to Symbolics' boolean operators `&`, `|` and `!`; they only
#   occur inside an `ifelse` condition in `@equations` (checked by the front end).
# * Intrinsics and discrete samplers (`interp1`, `interp2`, `delay`, `noise_normal`,
#   `previous`, `hold`, `reinit`) are not part of the continuous M1 lowering. They raise a
#   `LowerError` that `simulate` reports as E900 with the block path; the work packages that
#   add them (J2.2, J2.3, J2.7b) extend this table. Nothing here silently returns zero.

"""
    LowerError(message, path, block, range)

A construct the continuous lowering of this milestone cannot express, with the provenance
of the offending equation. `simulate` turns it into the E900 diagnostic of plan section 5.11;
the message ends up in the diagnostic's `hint` so the user sees which construct failed.
"""
struct LowerError <: Exception
    message::String
    path::Union{String,Nothing}
    block::Union{String,Nothing}
    range::Union{SourceRange,Nothing}
end

LowerError(message::AbstractString, origin::Union{Flat.Origin,Nothing}) = LowerError(
    String(message),
    origin === nothing ? nothing : origin.path,
    origin === nothing ? nothing : origin.block,
    origin === nothing ? nothing : origin.range,
)

function Base.showerror(io::IO, e::LowerError)
    print(io, e.message)
    e.path === nothing || print(io, " (in ", e.path, ")")
    return nothing
end

"""
    LowerCtx

The state shared by the expression walker: the signal-id → symbolic-variable maps, the extra
states created by `int`, the equations those states need, and the provenance of the equation
currently being lowered.
"""
mutable struct LowerCtx
    vars::Dict{String,Num}
    params::Dict{String,Num}
    int_states::Vector{Pair{Num,Any}}
    int_equations::Vector{Any}
    counter::Base.RefValue{Int}
    origin::Union{Flat.Origin,Nothing}
end

LowerCtx(vars::Dict{String,Num}, params::Dict{String,Num}) =
    LowerCtx(vars, params, Pair{Num,Any}[], Any[], Ref(0), nothing)

_lower_error(message::AbstractString, ctx::LowerCtx) =
    throw(LowerError(message, ctx.origin))

"""    lower_expression(e, ctx) -> Any

Lower one scalar AST node to a Symbolics value. The result is a `Num` for symbolic nodes and
a Julia number for literals; arrays are returned as Julia arrays for the few contexts that
still need them (intrinsic arguments in later milestones).
"""
function lower_expression(e::Lit, ::LowerCtx)
    v = e.value
    if v isa Bool || v isa Integer || v isa AbstractFloat
        return v
    end
    throw(LowerError("literal $(repr(v)) cannot appear in an expression", nothing))
end

function lower_expression(e::Name, ctx::LowerCtx)
    e.name === :t && return t
    key = String(e.name)
    haskey(ctx.vars, key) && return ctx.vars[key]
    haskey(ctx.params, key) && return ctx.params[key]
    return _lower_error("unknown name `$key` in a lowered expression", ctx)
end

function lower_expression(e::Field, ctx::LowerCtx)
    key = Flat.flat_id(e)
    haskey(ctx.vars, key) && return ctx.vars[key]
    haskey(ctx.params, key) && return ctx.params[key]
    return _lower_error("unknown port field `$key` in a lowered expression", ctx)
end

function lower_expression(e::BinOp, ctx::LowerCtx)
    lhs = lower_expression(e.lhs, ctx)
    rhs = lower_expression(e.rhs, ctx)
    op = e.op
    op === :+ && return lhs + rhs
    op === :- && return lhs - rhs
    op === :* && return lhs * rhs
    op === :/ && return lhs / rhs
    op === Symbol("\\") && return rhs / lhs
    op === :^ && return lhs^rhs
    return _lower_error("operator `$op` cannot be lowered", ctx)
end

function lower_expression(e::UnOp, ctx::LowerCtx)
    x = lower_expression(e.operand, ctx)
    e.op === :- && return -x
    e.op === :+ && return x
    e.op === Symbol("!") && return !x
    return _lower_error("unary operator `$(e.op)` cannot be lowered", ctx)
end

function lower_expression(e::IfElse, ctx::LowerCtx)
    cond = lower_expression(e.cond, ctx)
    then = lower_expression(e.then, ctx)
    otherwise = lower_expression(e.otherwise, ctx)
    return ifelse(cond, then, otherwise)
end

function lower_expression(e::Comparison, ctx::LowerCtx)
    lhs = lower_expression(e.lhs, ctx)
    rhs = lower_expression(e.rhs, ctx)
    op = e.op
    op === :< && return lhs < rhs
    op === :<= && return lhs <= rhs
    op === :> && return lhs > rhs
    op === :>= && return lhs >= rhs
    op === Symbol("==") && return lhs == rhs
    op === Symbol("!=") && return lhs != rhs
    return _lower_error("comparison `$op` cannot be lowered", ctx)
end

function lower_expression(e::BoolOp, ctx::LowerCtx)
    values = [lower_expression(a, ctx) for a in e.operands]
    isempty(values) && return _lower_error("empty boolean expression", ctx)
    if e.op === Symbol("&&")
        out = values[1]
        for v in values[2:end]
            out = out & v
        end
        return out
    elseif e.op === Symbol("||")
        out = values[1]
        for v in values[2:end]
            out = out | v
        end
        return out
    elseif e.op === Symbol("!")
        length(values) == 1 || return _lower_error("`!` takes one operand", ctx)
        return !values[1]
    end
    return _lower_error("boolean operator `$(e.op)` cannot be lowered", ctx)
end

# ---------------------------------------------------------------------------------------
# Indexing and array literals
# ---------------------------------------------------------------------------------------

# The flattener expands arrays into `x[1]`-style scalar ids, so an `Index` normally does not
# survive. Keep the literal-index case for the later scopes (@initial, @events) that reuse
# this walker with a non-expanded AST.
function _literal_index_id(e::Index)
    indices = Int[]
    for i in e.indices
        i isa Lit && i.value isa Integer || return nothing
        push!(indices, Int(i.value))
    end
    if e.base isa Name
        return String(e.base.name) * "[" * join(indices, ",") * "]"
    elseif e.base isa Field
        return Flat.flat_id(e.base) * "[" * join(indices, ",") * "]"
    end
    return nothing
end

function lower_expression(e::Index, ctx::LowerCtx)
    key = _literal_index_id(e)
    key !== nothing && haskey(ctx.vars, key) && return ctx.vars[key]
    return _lower_error("array index `$(sprint(show, e))` cannot be lowered", ctx)
end

function lower_expression(e::VectorLit, ctx::LowerCtx)
    return [lower_expression(x, ctx) for x in e.elements]
end

function lower_expression(e::MatrixLit, ctx::LowerCtx)
    isempty(e.rows) && return Any[]
    ncols = length(e.rows[1])
    all(row -> length(row) == ncols, e.rows) ||
        return _lower_error("matrix literal rows have different lengths", ctx)
    return [lower_expression(e.rows[r][c], ctx) for r in eachindex(e.rows), c in 1:ncols]
end

# ---------------------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------------------

_one_arg(args, fn, ctx) = length(args) == 1 ? args[1] :
                          _lower_error("`$fn` takes one argument", ctx)

function lower_expression(e::Call, ctx::LowerCtx)
    return lower_call(e.fn.name, e.args, ctx, e)
end

"""
    lower_call(fn::Symbol, args, ctx, node) -> Any

Lower one whitelisted call. `node` is the source node (used only for its range).
"""
function lower_call(fn::Symbol, args, ctx::LowerCtx, node)
    # Special forms that are not plain function calls.
    if fn === :ddt
        length(args) == 1 || return _lower_error("`ddt` takes one argument", ctx)
        return D(lower_expression(args[1], ctx))
    elseif fn === :int
        length(args) == 2 || return _lower_error("`int` takes two arguments", ctx)
        return _lower_int(args[1], args[2], ctx)
    elseif fn === :ifelse
        length(args) == 3 || return _lower_error("`ifelse` takes three arguments", ctx)
        return ifelse(
            lower_expression(args[1], ctx),
            lower_expression(args[2], ctx),
            lower_expression(args[3], ctx),
        )
    end

    # Nonsmooth functions become explicit `ifelse` forms (see the file header).
    if fn === :abs
        x = _one_arg(lower_args(args, ctx), fn, ctx)
        return ifelse(x < 0, -x, x)
    elseif fn === :sign
        x = _one_arg(lower_args(args, ctx), fn, ctx)
        return ifelse(x > 0, 1.0, ifelse(x < 0, -1.0, 0.0))
    elseif fn === :min || fn === :max || fn === :clamp || fn === :saturate ||
           fn === :deadzone
        return lower_nonsmooth(fn, lower_args(args, ctx), ctx)
    elseif fn === :round
        length(args) == 1 || return _lower_error("`round` takes one argument", ctx)
        x = lower_expression(args[1], ctx)
        # `round` is round-half-away-from-zero; floor/ceil are native Symbolics heads.
        return ifelse(x >= 0, floor(x + 0.5), ceil(x - 0.5))
    elseif fn === :hypot
        length(args) == 2 || return _lower_error("`hypot` takes two arguments", ctx)
        a = lower_expression(args[1], ctx)
        b = lower_expression(args[2], ctx)
        return hypot(a, b)
    end

    # Pure scalar functions that Symbolics implements directly.
    if fn in (:sin, :cos, :tan, :asin, :acos, :sinh, :cosh, :tanh, :exp, :log, :log10,
        :sqrt, :floor, :ceil)
        length(args) == 1 || return _lower_error("`$fn` takes one argument", ctx)
        x = lower_expression(args[1], ctx)
        fn === :sin && return sin(x)
        fn === :cos && return cos(x)
        fn === :tan && return tan(x)
        fn === :asin && return asin(x)
        fn === :acos && return acos(x)
        fn === :sinh && return sinh(x)
        fn === :cosh && return cosh(x)
        fn === :tanh && return tanh(x)
        fn === :exp && return exp(x)
        fn === :log && return log(x)
        fn === :log10 && return log10(x)
        fn === :sqrt && return sqrt(x)
        fn === :floor && return floor(x)
        fn === :ceil && return ceil(x)
    elseif fn === :mod || fn === :rem
        length(args) == 2 || return _lower_error("`$fn` takes two arguments", ctx)
        a = lower_expression(args[1], ctx)
        b = lower_expression(args[2], ctx)
        return fn === :mod ? mod(a, b) : rem(a, b)
    elseif fn === :atan
        values = lower_args(args, ctx)
        length(values) == 1 && return atan(values[1])
        length(values) == 2 && return atan(values[1], values[2])
        return _lower_error("`atan` takes one or two arguments", ctx)
    elseif fn === :dot
        values = lower_args(args, ctx)
        length(values) == 2 || return _lower_error("`dot` takes two arguments", ctx)
        a, b = values
        if a isa AbstractArray && b isa AbstractArray
            length(a) == length(b) || return _lower_error("`dot` sizes differ", ctx)
            return sum(a[k] * b[k] for k in eachindex(a))
        end
        return a * b
    elseif fn === :norm
        values = lower_args(args, ctx)
        x = _one_arg(values, fn, ctx)
        return x isa AbstractArray ? sqrt(sum(abs2, x)) : abs(x)
    elseif fn === :cross
        values = lower_args(args, ctx)
        length(values) == 2 || return _lower_error("`cross` takes two arguments", ctx)
        a, b = values
        (a isa AbstractVector && b isa AbstractVector && length(a) == 3 &&
         length(b) == 3) || return _lower_error("`cross` needs two 3-vectors", ctx)
        return [
            a[2] * b[3] - a[3] * b[2],
            a[3] * b[1] - a[1] * b[3],
            a[1] * b[2] - a[2] * b[1],
        ]
    elseif fn === :transpose
        values = lower_args(args, ctx)
        x = _one_arg(values, fn, ctx)
        x isa AbstractMatrix && return permutedims(x)
        x isa AbstractVector && return x
        return _lower_error("`transpose` needs a vector or matrix", ctx)
    end

    # Discrete, event or M2 constructs. J2.2/J2.3/J2.7b extend this table; a clear error is
    # better than silently inventing a value.
    fn in (:previous, :hold, :reinit) && return _lower_error(
        "`$fn` is only lowered for discrete/event code (J2.2/J2.3)", ctx
    )
    fn in (:delay, :interp1, :interp2, :noise_normal) && return _lower_error(
        "`$fn` is an intrinsic that this continuous build does not lower yet (J2.7b)", ctx
    )
    return _lower_error("function `$fn` cannot be lowered", ctx)
end

function lower_args(args, ctx::LowerCtx)
    return [lower_expression(a, ctx) for a in args]
end

function lower_nonsmooth(fn::Symbol, values, ctx::LowerCtx)
    if fn === :min
        2 <= length(values) <= 3 || return _lower_error("`min` takes two or three arguments", ctx)
        out = values[1]
        for v in values[2:end]
            out = ifelse(out <= v, out, v)
        end
        return out
    elseif fn === :max
        2 <= length(values) <= 3 || return _lower_error("`max` takes two or three arguments", ctx)
        out = values[1]
        for v in values[2:end]
            out = ifelse(out >= v, out, v)
        end
        return out
    elseif fn === :clamp || fn === :saturate
        length(values) in (2, 3) || return _lower_error(
            "`$fn` takes two or three arguments", ctx
        )
        if length(values) == 2
            x, hi = values
            lo = -hi
        else
            x, lo, hi = values
        end
        return ifelse(x < lo, lo, ifelse(x > hi, hi, x))
    elseif fn === :deadzone
        length(values) in (2, 3) || return _lower_error(
            "`deadzone` takes two or three arguments", ctx
        )
        if length(values) == 2
            x, hi = values
            lo = -hi
        else
            x, lo, hi = values
        end
        return ifelse(x > hi, x - hi, ifelse(x < lo, x - lo, 0.0))
    end
    return _lower_error("`$fn` cannot be lowered", ctx)
end

# ---------------------------------------------------------------------------------------
# `int(x, x0)`
# ---------------------------------------------------------------------------------------

"""
    _lower_int(x, x0, ctx) -> Num

Create the hidden state of `int(x, x0)`: a fresh scalar named from the origin path and a
per-model counter, with `D(state) ~ x` appended to the system and `x0` remembered as an AST
so the run can evaluate it with the parameter values of that run (D4).
"""
function _lower_int(x, x0, ctx::LowerCtx)
    ctx.counter[] += 1
    path = ctx.origin === nothing ? "model" : something(ctx.origin.path, "model")
    name = "__bgint/" * path * "/" * string(ctx.counter[])
    state = mtk_variable(name)
    rhs = lower_expression(x, ctx)
    push!(ctx.int_equations, D(state) ~ rhs)
    push!(ctx.int_states, state => x0)
    return state
end
