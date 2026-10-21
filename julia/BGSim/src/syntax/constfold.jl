# Constant folding, never `eval` (plan 4.3: "They are evaluated at instantiation by a small
# constant-folding interpreter, never by `eval`").
#
# Used by the parser for structural sizes and by the catalog for constant values. It folds
# literals, `@constants`, other parameters with a known default, and the whitelisted *pure*
# functions. It refuses everything else with a `ConstFoldError`, which the checker turns into
# E004 ("not a constant expression").

"""    ConstFoldError(message)

Raised by [`eval_const`](@ref) when an expression is not a constant expression."""
struct ConstFoldError <: Exception
    message::String
end

Base.showerror(io::IO, e::ConstFoldError) = print(io, e.message)

_fold_name(name::Symbol, env::AbstractDict) =
    haskey(env, name) ? env[name] :
    throw(ConstFoldError("`$name` is not a constant"))

function _fold_dot(a, b)
    length(a) == length(b) ||
        throw(ConstFoldError("dot needs two vectors of the same length"))
    return sum(a[i] * b[i] for i in eachindex(a))
end

function _fold_norm(a)
    return sqrt(sum(abs2(x) for x in a))
end

function _fold_cross(a, b)
    (length(a) == 3 && length(b) == 3) ||
        throw(ConstFoldError("cross needs two 3-vectors"))
    return [
        a[2] * b[3] - a[3] * b[2],
        a[3] * b[1] - a[1] * b[3],
        a[1] * b[2] - a[2] * b[1],
    ]
end

function _fold_transpose(a)
    a isa AbstractMatrix && return permutedims(a)
    a isa AbstractVector && return a
    throw(ConstFoldError("transpose needs a vector or a matrix"))
end

function _fold_call(fn::Symbol, args::Vector{Any})
    if fn === :abs
        return abs(args[1])
    elseif fn === :sign
        return sign(args[1])
    elseif fn === :min
        return min(args...)
    elseif fn === :max
        return max(args...)
    elseif fn === :clamp
        return clamp(args...)
    elseif fn === :floor
        return floor(args[1])
    elseif fn === :ceil
        return ceil(args[1])
    elseif fn === :round
        return round(args[1])
    elseif fn === :sqrt
        return sqrt(args[1])
    elseif fn === :exp
        return exp(args[1])
    elseif fn === :log
        return log(args[1])
    elseif fn === :log10
        return log10(args[1])
    elseif fn === :sin
        return sin(args[1])
    elseif fn === :cos
        return cos(args[1])
    elseif fn === :tan
        return tan(args[1])
    elseif fn === :asin
        return asin(args[1])
    elseif fn === :acos
        return acos(args[1])
    elseif fn === :atan
        return length(args) == 1 ? atan(args[1]) : atan(args[1], args[2])
    elseif fn === :sinh
        return sinh(args[1])
    elseif fn === :cosh
        return cosh(args[1])
    elseif fn === :tanh
        return tanh(args[1])
    elseif fn === :mod
        args[2] == 0 && throw(ConstFoldError("division by zero in `mod`"))
        return mod(args[1], args[2])
    elseif fn === :rem
        args[2] == 0 && throw(ConstFoldError("division by zero in `rem`"))
        return rem(args[1], args[2])
    elseif fn === :hypot
        return hypot(args[1], args[2])
    elseif fn === :dot
        return _fold_dot(args[1], args[2])
    elseif fn === :norm
        return _fold_norm(args[1])
    elseif fn === :cross
        return _fold_cross(args[1], args[2])
    elseif fn === :transpose
        return _fold_transpose(args[1])
    end
    throw(ConstFoldError("`$fn` is not a pure function"))
end

"""
    eval_const(e::Expr, env = Dict{Symbol,Any}()) -> Any

Fold a constant expression. `env` maps `@constants` names and parameters with known defaults
to values. Throws [`ConstFoldError`](@ref) for anything that is not constant: a variable, a
port, `t`, an unknown name, or a non-pure function.

This is a plain interpreter over our own AST; it never calls `eval`, `Meta.parse` or
`include` on user text.
"""
function eval_const(e::Expr, env::AbstractDict = Dict{Symbol,Any}())
    if e isa Lit
        return e.value
    elseif e isa Name
        return _fold_name(e.name, env)
    elseif e isa BinOp
        a = eval_const(e.lhs, env)
        b = eval_const(e.rhs, env)
        if e.op === :+
            return a + b
        elseif e.op === :-
            return a - b
        elseif e.op === :*
            return a * b
        elseif e.op === :/
            b == 0 && throw(ConstFoldError("division by zero"))
            return a / b
        elseif e.op === :\
            b == 0 && throw(ConstFoldError("division by zero"))
            return a \ b
        elseif e.op === :^
            return a^b
        end
        throw(ConstFoldError("operator `$(e.op)` is not allowed in a constant expression"))
    elseif e isa UnOp
        a = eval_const(e.operand, env)
        e.op === :- && return -a
        e.op === :+ && return +a
        e.op === :! && return !a
        throw(ConstFoldError("operator `$(e.op)` is not allowed in a constant expression"))
    elseif e isa Call
        args = Any[eval_const(a, env) for a in e.args]
        return _fold_call(e.fn.name, args)
    elseif e isa Index
        base = eval_const(e.base, env)
        idx = [eval_const(i, env) for i in e.indices]
        if base isa AbstractVector
            length(idx) == 1 ||
                throw(ConstFoldError("a vector takes one index, got $(length(idx))"))
            i = Int(idx[1])
            (1 <= i <= length(base)) ||
                throw(ConstFoldError("index $i is out of range for a vector of length $(length(base))"))
            return base[i]
        elseif base isa AbstractMatrix
            length(idx) == 2 ||
                throw(ConstFoldError("a matrix takes two indices, got $(length(idx))"))
            i, j = Int(idx[1]), Int(idx[2])
            (1 <= i <= size(base, 1) && 1 <= j <= size(base, 2)) ||
                throw(ConstFoldError("index ($i, $j) is out of range"))
            return base[i, j]
        end
        throw(ConstFoldError("cannot index a scalar"))
    elseif e isa VectorLit
        return [eval_const(a, env) for a in e.elements]
    elseif e isa MatrixLit
        rows = [[eval_const(a, env) for a in row] for row in e.rows]
        isempty(rows) && return Matrix{Float64}(undef, 0, 0)
        n = length(rows[1])
        all(length(r) == n for r in rows) ||
            throw(ConstFoldError("matrix literal rows must all have the same length"))
        return permutedims(hcat(rows...))
    elseif e isa IfElse
        cond = eval_const(e.cond, env)
        cond isa Bool || throw(ConstFoldError("`ifelse` condition is not a Bool constant"))
        return cond ? eval_const(e.then, env) : eval_const(e.otherwise, env)
    elseif e isa Comparison
        a = eval_const(e.lhs, env)
        b = eval_const(e.rhs, env)
        e.op === :< && return a < b
        e.op === :<= && return a <= b
        e.op === :> && return a > b
        e.op === :>= && return a >= b
        e.op === Symbol("==") && return a == b
        e.op === Symbol("!=") && return a != b
        throw(ConstFoldError("unknown comparison `$(e.op)`"))
    elseif e isa BoolOp
        vals = Bool[eval_const(a, env) for a in e.operands]
        e.op === Symbol("&&") && return all(vals)
        e.op === Symbol("||") && return any(vals)
        e.op === Symbol("!") && return !vals[1]
        throw(ConstFoldError("unknown logical operator `$(e.op)`"))
    elseif e isa Field
        throw(ConstFoldError("a port field is not a constant"))
    end
    throw(ConstFoldError("not a constant expression"))
end

"""
    try_eval_const(e, env) -> Tuple{Bool,Any}

`(true, value)` when `e` folds, `(false, message)` when it does not. Used for attributes and
defaults, where the checker reports E004 rather than throwing.
"""
function try_eval_const(e::Expr, env::AbstractDict = Dict{Symbol,Any}())
    try
        return true, eval_const(e, env)
    catch err
        err isa ConstFoldError || rethrow()
        return false, err.message
    end
end

"""    eval_const_number(e, env) -> Union{Int,Float64,Nothing}

Fold to a number, or `nothing` when `e` is not a numeric constant."""
function eval_const_number(e::Expr, env::AbstractDict = Dict{Symbol,Any}())
    ok, value = try_eval_const(e, env)
    ok || return nothing
    value isa Bool && return nothing
    value isa Integer && return Int(value)
    value isa AbstractFloat && return Float64(value)
    return nothing
end
