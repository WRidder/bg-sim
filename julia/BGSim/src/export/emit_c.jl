# Symbolic expression -> C99 expression (plan/EXPORT_PLAN.md D-EX1, D-EX8).
#
# `cexpr` walks a SymbolicUtils tree of the `mtkcompile`d system. Every leaf must already be
# in `env` (state, parameter, held value, input, observed local, `t`) or be a constant; every
# operation must have a C spelling here. Anything else throws an `ExportError`, which
# `export_model` reports as E110. Nothing is guessed: an unknown operation never becomes a
# call to a function of the same name.
#
# The semantics follow the Julia lowering exactly: `sign(-0.0) == 0.0`, `round` is half away
# from zero, `min`/`max` are Julia's (non-NaN) definitions, `mod` takes the divisor's sign.
# They live in `bg_runtime.h`.

"""    ExportError(message)

A construct the C emitter cannot lower. `export_model` turns it into E110."""
struct ExportError <: Exception
    message::String
end

Base.showerror(io::IO, e::ExportError) = print(io, e.message)

clit(v::Bool) = v ? "1.0" : "0.0"
function clit(v::Real)
    f = Float64(v)
    isnan(f) && return "NAN"
    isinf(f) && return f > 0 ? "INFINITY" : "(-INFINITY)"
    s = repr(f)
    return f < 0 ? "($s)" : s
end
clit(v) = throw(ExportError("the constant `$v` ($(typeof(v))) has no C literal"))

function _try_const(x)
    x isa Number && return x
    if isdefined(SymbolicUtils, :isconst) && SymbolicUtils.isconst(x)
        return SymbolicUtils.unwrap_const(x)
    end
    return nothing
end

const C_MATH1 = Dict{Any,String}(
    sin => "sin", cos => "cos", tan => "tan", asin => "asin", acos => "acos",
    sinh => "sinh", cosh => "cosh", tanh => "tanh", exp => "exp", log => "log",
    log10 => "log10", sqrt => "sqrt", abs => "fabs", floor => "floor", ceil => "ceil",
    sign => "bg_sign", round => "bg_round",
)

const C_CMP = Dict{Any,String}(
    (>=) => ">=", (>) => ">", (<=) => "<=", (<) => "<", (==) => "==", (!=) => "!=",
)

"""    cexpr(x, env, modes = nothing) -> String

The C expression of `x`. With `modes` (a vector), every `ifelse` condition becomes a frozen
mode value `m->c[k]` and is appended to `modes` once (D-EX8); `bg_modes` evaluates them at
the start of each step."""
function cexpr(x, env::Dict{Any,String}, modes = nothing)
    x = Symbolics.unwrap(x)
    s = get(env, x, nothing)
    s === nothing || return s
    c = _try_const(x)
    c === nothing || return clit(c)
    SymbolicUtils.iscall(x) ||
        throw(ExportError("`$x` is not a state, parameter, input or observed variable of the compiled system"))
    op = SymbolicUtils.operation(x)
    args = SymbolicUtils.arguments(x)
    r = cexpr_intrinsic(op, args, env, modes)  # interp, CSV, mechanics (emit_intrinsics.jl)
    r === nothing || return r
    if op === ifelse && modes !== nothing
        cond = Symbolics.unwrap(args[1])
        k = findfirst(c -> isequal(c, cond), modes)
        k === nothing && (push!(modes, cond); k = length(modes))
        return "((m->c[$(k - 1)] != 0.0) ? $(cexpr(args[2], env, modes)) : $(cexpr(args[3], env, modes)))"
    end
    if any(_is_array_literal, args)  # a table argument (interp1/interp2 over constant arrays)
        throw(ExportError("`$(nameof_op(op))` with table arguments has no C implementation yet (plan J-EX5)"))
    end
    a = String[cexpr(y, env, modes) for y in args]
    if op === (+)
        return "(" * join(a, " + ") * ")"
    elseif op === (*)
        return "(" * join(a, " * ") * ")"
    elseif op === (-)
        return length(a) == 1 ? "(-$(a[1]))" : "($(a[1]) - $(a[2]))"
    elseif op === (/)
        return "($(a[1]) / $(a[2]))"
    elseif op === (^)
        e = _try_const(Symbolics.unwrap(args[2]))
        e == 2 && return "($(a[1]) * $(a[1]))"
        e == -1 && return "(1.0 / $(a[1]))"
        return "pow($(a[1]), $(a[2]))"
    elseif op === ifelse
        return "(($(a[1])) ? $(a[2]) : $(a[3]))"
    elseif haskey(C_CMP, op)
        return "($(a[1]) $(C_CMP[op]) $(a[2]))"
    elseif op === (&)
        return "(" * join(a, " && ") * ")"
    elseif op === (|)
        return "(" * join(a, " || ") * ")"
    elseif op === (!)
        return "(!$(a[1]))"
    elseif op === atan
        return length(a) == 2 ? "atan2($(a[1]), $(a[2]))" : "atan($(a[1]))"
    elseif op === min
        return "bg_min($(a[1]), $(a[2]))"
    elseif op === max
        return "bg_max($(a[1]), $(a[2]))"
    elseif op === hypot
        return "hypot($(a[1]), $(a[2]))"
    elseif op === mod
        return "bg_mod($(a[1]), $(a[2]))"
    elseif op === rem
        return "fmod($(a[1]), $(a[2]))"
    elseif haskey(C_MATH1, op) && length(a) == 1
        return "$(C_MATH1[op])($(a[1]))"
    end
    throw(ExportError("`$(nameof_op(op))` has no C implementation yet (in `$x`)"))
end

function _is_array_literal(y)
    y = Symbolics.unwrap(y)
    return SymbolicUtils.iscall(y) && SymbolicUtils.operation(y) === SymbolicUtils.array_literal
end

nameof_op(op) = try
    string(nameof(op))
catch
    string(op)
end

"""    needed_observed(exprs, obs) -> BitVector

The observed equations `exprs` need, transitively (observed are topologically ordered)."""
function needed_observed(exprs, obs)
    need = falses(length(obs.rhs))
    stack = Any[]
    for e in exprs
        u = Symbolics.unwrap(e)
        haskey(obs.index, u) && push!(stack, u)
        append!(stack, Symbolics.get_variables(u))
    end
    while !isempty(stack)
        v = Symbolics.unwrap(pop!(stack))
        k = get(obs.index, v, 0)
        (k == 0 || need[k]) && continue
        need[k] = true
        append!(stack, Symbolics.get_variables(obs.rhs[k]))
    end
    return need
end

"""    emit_function(io, signature, targets, env, obs; modes = nothing)

One C function: the observed locals the targets need (in observed order, so each is a
common subexpression computed once), then one `target = expr;` per `(target, expr, comment)`."""
function emit_function(io, signature, targets, env, obs; modes = nothing)
    need = needed_observed(Any[t[2] for t in targets], obs)
    println(io, signature, " {")
    println(io, "    (void)m; (void)t; (void)x;")
    local_env = copy(env)
    begin_intrinsic_scope()
    for k in eachindex(obs.rhs)
        need[k] || continue
        cname = "o$(k - 1)"
        rhs = cexpr(obs.rhs[k], local_env, modes)
        flush_intrinsic_statements(io)
        println(io, "    const double $cname = $rhs; /* $(ccomment(obs.names[k])) */")
        local_env[obs.lhs[k]] = cname
    end
    for (target, e, comment) in targets
        rhs = cexpr(e, local_env, modes)
        flush_intrinsic_statements(io)
        println(io, "    $target = $rhs;", comment === nothing ? "" : " /* $(ccomment(comment)) */")
    end
    end_intrinsic_scope()
    println(io, "}\n")
end

# A comment must not close itself.
ccomment(s) = replace(string(s), "*/" => "* /")
