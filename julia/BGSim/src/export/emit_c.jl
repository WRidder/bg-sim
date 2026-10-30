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
    if op === ifelse && modes !== nothing
        cond = Symbolics.unwrap(args[1])
        k = findfirst(c -> isequal(c, cond), modes)
        k === nothing && (push!(modes, cond); k = length(modes))
        return "((m->c[$(k - 1)] != 0.0) ? $(cexpr(args[2], env, modes)) : $(cexpr(args[3], env, modes)))"
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
    local_env = copy(env)
    locals = _observed_locals(Any[t[2] for t in targets], obs, local_env, modes)
    body = [(target, cexpr(e, local_env, modes), comment) for (target, e, comment) in targets]
    keep = _used_locals(locals, String[b[2] for b in body])
    println(io, signature, " {")
    println(io, "    (void)m; (void)t; (void)x;")
    for (i, (name, code, comment)) in enumerate(locals)
        keep[i] && println(io, "    const double $name = $code; /* $(ccomment(comment)) */")
    end
    for (target, code, comment) in body
        println(io, "    $target = $code;", comment === nothing ? "" : " /* $(ccomment(comment)) */")
    end
    println(io, "}\n")
end

"""    _observed_locals(exprs, obs, local_env, modes) -> Vector{(name, code, comment)}

The observed locals `exprs` need, in observed order, as C; `local_env` learns their names."""
function _observed_locals(exprs, obs, local_env, modes)
    need = needed_observed(exprs, obs)
    out = Tuple{String,String,String}[]
    for k in eachindex(obs.rhs)
        need[k] || continue
        cname = "o$(k - 1)"
        push!(out, (cname, cexpr(obs.rhs[k], local_env, modes), obs.names[k]))
        local_env[obs.lhs[k]] = cname
    end
    return out
end

"""    _used_locals(locals, code) -> BitVector

Which observed locals the C `code` reads, directly or through a kept local. A variable that
appears only in a frozen switching condition is read through `m->c`, so its local would be
unused (and fail -Werror)."""
function _used_locals(locals, code::Vector{String})
    used = Set{String}()
    scan(s) = for mm in eachmatch(r"\bo[0-9]+\b", s)
        push!(used, mm.match)
    end
    foreach(scan, code)
    keep = falses(length(locals))
    for i in length(locals):-1:1          # a local reads only earlier ones
        locals[i][1] in used || continue
        keep[i] = true
        scan(locals[i][2])
    end
    return keep
end

# A comment must not close itself.
ccomment(s) = replace(string(s), "*/" => "* /")

# ---------------------------------------------------------------------------------------
# The Jacobian (D-EX12)
# ---------------------------------------------------------------------------------------

"""Thrown when the symbolic Jacobian exceeds its size or time guard."""
struct JacobianTooBig <: Exception
    reason::String
end

_is_zero(e) = (c = _try_const(e); c !== nothing && iszero(c)) ||
    (SymbolicUtils.iscall(e) && SymbolicUtils.operation(e) === ifelse &&
     all(a -> _is_zero(Symbolics.unwrap(a)), SymbolicUtils.arguments(e)[2:3]))

_is_one(e) = (c = _try_const(e); c !== nothing && isone(c))

# A C expression that is a plain name or literal can be repeated; anything else is computed
# once into a local.
_simple_c(s) = occursin(r"^[A-Za-z_][A-Za-z0-9_]*$|^\(?-?[0-9.]+(e[+-]?[0-9]+)?\)?$", s)

"""    jacobian_c(rhs, xs, obs, env, modes; max_terms, max_seconds) -> NamedTuple

The body of `bg_jacobian` (`J = ∂f/∂x`, row-major, only the structural non-zeros written),
by forward accumulation through the observed equations instead of differentiating the
substituted right-hand side, which blows up on multibody models. For every observed local
`o_k` the derivatives `∂o_k/∂x_j` become C locals, so each partial of each equation is
computed once (common subexpressions by construction):

    ∂o_k/∂x_j = Σ_v ∂rhs_k/∂v · ∂v/∂x_j      v a state or an earlier observed variable

Only the derivatives some row needs are emitted. Throws `JacobianTooBig` when the number of
terms exceeds `max_terms` or the build takes longer than `max_seconds`, and an `ExportError`
when a partial has no C form; the caller then falls back to finite differences. Returns
`(code, terms, entries)`."""
function jacobian_c(rhs, xs, obs, env::Dict{Any,String}, modes; max_terms::Int = 200_000,
    max_seconds::Real = 120.0)
    t0 = time()
    guard() = time() - t0 > max_seconds &&
        throw(JacobianTooBig("the symbolic Jacobian took more than $(max_seconds) s"))
    nx = length(xs)
    nobs = length(obs.rhs)
    xidx = Dict{Any,Int}(x => i for (i, x) in enumerate(xs))
    relevant(v) = haskey(xidx, v) || haskey(obs.index, v)
    function partials(e)
        out = Tuple{Any,Any}[]
        e = Symbolics.unwrap(e)
        for v in Symbolics.get_variables(e)
            relevant(v) || continue
            p = Symbolics.unwrap(Symbolics.derivative(e, v))
            _is_zero(p) || push!(out, (v, p))
        end
        guard()
        return out
    end
    need = needed_observed(rhs, obs)
    part_obs = Vector{Vector{Tuple{Any,Any}}}(undef, nobs)
    for k in 1:nobs
        part_obs[k] = need[k] ? partials(obs.rhs[k]) : Tuple{Any,Any}[]
    end
    part_rhs = [partials(r) for r in rhs]
    # Backward: the observed whose derivatives some row uses, transitively.
    dneed = falses(nobs)
    stack = Int[obs.index[v] for pr in part_rhs for (v, _) in pr if haskey(obs.index, v)]
    while !isempty(stack)
        k = pop!(stack)
        dneed[k] && continue
        dneed[k] = true
        for (v, _) in part_obs[k]
            haskey(obs.index, v) && push!(stack, obs.index[v])
        end
    end
    pexprs = Any[p for k in 1:nobs if dneed[k] for (_, p) in part_obs[k]]
    for pr in part_rhs, (_, p) in pr
        push!(pexprs, p)
    end
    io = IOBuffer()
    local_env = copy(env)
    locals = _observed_locals(pexprs, obs, local_env, modes)
    D = Vector{Dict{Int,String}}(undef, nobs)
    terms = 0
    nloc = 0
    function combine(pr)
        acc = Dict{Int,Vector{String}}()
        for (v, p) in pr
            src = haskey(xidx, v) ? Dict(xidx[v] => "1.0") : D[obs.index[v]]
            isempty(src) && continue
            pc = _is_one(p) ? "1.0" : cexpr(p, local_env, modes)
            if length(src) > 1 && !_simple_c(pc)
                name = "p$(nloc)"
                nloc += 1
                println(io, "    const double $name = $pc;")
                pc = name
            end
            for (j, dj) in src
                push!(get!(acc, j, String[]), pc == "1.0" ? dj : dj == "1.0" ? pc : "$pc * $dj")
            end
            terms += length(src)
            terms > max_terms &&
                throw(JacobianTooBig("the symbolic Jacobian needs more than $(max_terms) terms"))
        end
        guard()
        return acc
    end
    for k in 1:nobs
        dneed[k] || continue
        D[k] = Dict{Int,String}()
        acc = combine(part_obs[k])
        for j in sort!(collect(keys(acc)))
            list = acc[j]
            if length(list) == 1 && _simple_c(list[1])
                D[k][j] = list[1]
            else
                name = "d$(k - 1)_$(j - 1)"
                println(io, "    const double $name = $(join(list, " + ")); /* d $(ccomment(obs.names[k])) / dx[$(j - 1)] */")
                D[k][j] = name
            end
        end
    end
    entries = 0
    for i in 1:nx
        acc = combine(part_rhs[i])
        for j in sort!(collect(keys(acc)))
            println(io, "    J[$((i - 1) * nx + (j - 1))] = $(join(acc[j], " + "));")
            entries += 1
        end
    end
    body = String(take!(io))
    # Comments carry signal names, so only the code before them is scanned for reads.
    keep = _used_locals(locals, String[first(split(l, "/*")) for l in split(body, '\n')])
    out = IOBuffer()
    for (i, (name, code, comment)) in enumerate(locals)
        keep[i] && println(out, "    const double $name = $code; /* $(ccomment(comment)) */")
    end
    print(out, body)
    return (code = String(take!(out)), terms = terms, entries = entries)
end

"""The body of a dense forward-difference `bg_jacobian`: `BG_NX + 1` derivative calls, with
stack buffers of fixed size (the temporary fallback of D-EX12; J-EX4 colours it)."""
const FD_JACOBIAN_C = """
        double xp[BG_SZ(BG_NX)], f0[BG_SZ(BG_NX)], f1[BG_SZ(BG_NX)];
        bg_derivatives(m, t, x, f0);
        for (int j = 0; j < BG_NX; ++j) xp[j] = x[j];
        for (int j = 0; j < BG_NX; ++j) {
            const double h = 1.4901161193847656e-8 * (fabs(x[j]) > 1.0 ? fabs(x[j]) : 1.0);
            xp[j] = x[j] + h;
            const double hh = xp[j] - x[j];
            bg_derivatives(m, t, xp, f1);
            for (int i = 0; i < BG_NX; ++i) J[i * BG_NX + j] = (f1[i] - f0[i]) / hh;
            xp[j] = x[j];
        }
    """

"""    op_count(exprs, obs) -> Int

A rough flop count of evaluating `exprs` with the observed locals they need (each once): 1
per arithmetic operation, 10 per function call. The cost model's unit."""
function op_count(exprs, obs)
    function count(e)
        e = Symbolics.unwrap(e)
        haskey(obs.index, e) && return 0
        SymbolicUtils.iscall(e) || return 0
        op = SymbolicUtils.operation(e)
        op isa SymbolicUtils.BasicSymbolic && return 0     # a variable x(t)
        op === getindex && return 0
        args = SymbolicUtils.arguments(e)
        w = op in (+, *, -, /) ? max(1, length(args) - 1) :
            (op === ifelse || haskey(C_CMP, op) || op in (&, |, !)) ? 1 : 10
        return w + sum(count, args; init = 0)
    end
    need = needed_observed(exprs, obs)
    total = sum(count, exprs; init = 0)
    for k in eachindex(obs.rhs)
        need[k] && (total += count(obs.rhs[k]))
    end
    return total
end
