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
    if any(_is_array_literal ∘ Symbolics.unwrap, args)  # a table argument (emit_intrinsics.jl) (interp1/interp2 over constant arrays)
        throw(ExportError("`$(nameof_op(op))` with table arguments has no C implementation yet (plan J-EX5)"))
    end
    simplify = C_SIMPLIFY[]
    simplify && op === (+) && return _c_sum(args, env, modes)
    a = String[cexpr(y, env, modes) for y in args]
    if op === (+)
        return "(" * join(a, " + ") * ")"
    elseif op === (*)
        simplify && return _c_product(a)
        return "(" * join(a, " * ") * ")"
    elseif op === (-)
        return length(a) == 1 ? "(-$(a[1]))" : "($(a[1]) - $(a[2]))"
    elseif op === (/)
        if simplify
            n, d = _lit_value(a[1]), _lit_value(a[2])
            d == 1 && return a[1]
            n !== nothing && d !== nothing && return clit(n / d)
        end
        return "($(a[1]) / $(a[2]))"
    elseif op === (^)
        e = _try_const(Symbolics.unwrap(args[2]))
        if simplify
            b, ev = _lit_value(a[1]), _lit_value(a[2])
            e === nothing && (e = ev)              # a folded exponent reached as a literal
            e == 1 && return a[1]
            e == 0 && return "1.0"                 # pow(x, 0) is 1 for every x
            if b !== nothing && ev !== nothing
                r = try
                    b^ev
                catch err
                    err isa DomainError || rethrow()
                    nothing
                end
                r === nothing || return clit(r)
            end
        end
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

"""Whether the emitter applies its peephole rules (`_c_product`, `_c_sum`, `x / 1`, `x^1`,
constant operands). Set from `ExportSettings.simplify` for one export; on by default."""
const C_SIMPLIFY = Base.ScopedValues.ScopedValue(true)

const _C_NUMBER = r"^\(?(-?[0-9]+(?:\.[0-9]*)?(?:e[+-]?[0-9]+)?)\)?$"

"""The value of a finite C literal written by `clit` (`1.0`, `(-2.5e-3)`), else `nothing`."""
function _lit_value(s::AbstractString)
    m = match(_C_NUMBER, s)
    m === nothing && return nothing
    return parse(Float64, m.captures[1])
end

"""    _c_product(a) -> String

A C product of the operand strings `a` with the leftovers of folding removed (D-EX10): the
literal operands are multiplied into one, a zero literal makes the product `0.0` (dropping
the NaN of an infinite operand), a unit literal is left out and `-1` becomes a negation."""
function _c_product(a::Vector{String}; exact::Bool = false)
    exact && return _c_product_exact(a)
    c = 1.0
    rest = String[]
    for s in a
        v = _lit_value(s)
        v === nothing ? push!(rest, s) : (c *= v)
    end
    iszero(c) && return "0.0"
    isempty(rest) && return clit(c)
    body = length(rest) == 1 ? rest[1] : "(" * join(rest, " * ") * ")"
    c == 1 && return body
    c == -1 && return "(-$body)"
    return "(" * join([clit(c); rest], " * ") * ")"
end

"""    _c_product_exact(a) -> String

The bit-exact subset of `_c_product`, for the discrete partitions (whose C must match the
Julia scheduler bit for bit): a `1.0` factor is left out and a `(-1.0)` factor becomes a
negation (both exact anywhere in a left-to-right product), and a product of literals only
is evaluated left to right as C would. A zero factor stays (`0.0 * x` is `-0.0` or NaN for
some `x`)."""
function _c_product_exact(a::Vector{String})
    vals = [_lit_value(s) for s in a]
    if all(!isnothing, vals)
        c = vals[1]
        for v in vals[2:end]
            c *= v
        end
        return clit(c)
    end
    neg = false
    rest = String[]
    for (s, v) in zip(a, vals)
        v == 1 && continue
        v == -1 && (neg = !neg; continue)
        push!(rest, s)
    end
    body = length(rest) == 1 ? rest[1] : "(" * join(rest, " * ") * ")"
    return neg ? "(-$body)" : body
end

"""The C of `-y` when `y` is a product with a negative numeric coefficient (how
SymbolicUtils writes a difference: `a - b` is `a + (-1)*b`), else `nothing`."""
function _negated_term(y, env, modes)
    SymbolicUtils.iscall(y) && SymbolicUtils.operation(y) === (*) || return nothing
    haskey(env, y) && return nothing
    args = SymbolicUtils.arguments(y)
    c = _try_const(Symbolics.unwrap(args[1]))
    (c isa Real && !(c isa Bool) && c < 0) || return nothing
    rest = String[cexpr(z, env, modes) for z in args[2:end]]
    return _c_product(c == -1 ? rest : [clit(-c); rest])
end

"""    _c_sum(args, env, modes) -> String

A C sum with the leftovers of folding removed (D-EX10): literal terms are added into one
and a zero is left out (`x + 0.0` is `x`, except for the sign of a negative zero); a term
with a negative coefficient is subtracted (`a - b` instead of `a + (-1.0) * b`, the same
value). The order of the other terms is kept, so the rounding is that of the sum as
written."""
function _c_sum(args, env, modes)
    terms = Tuple{Bool,String}[]
    lit = 0.0
    for y in args
        y = Symbolics.unwrap(y)
        neg = _negated_term(y, env, modes)
        if neg !== nothing
            neg == "0.0" || push!(terms, (true, neg))
            continue
        end
        s = cexpr(y, env, modes)
        v = _lit_value(s)
        v === nothing ? push!(terms, (false, s)) : (lit += v)
    end
    iszero(lit) || pushfirst!(terms, (false, clit(lit)))
    isempty(terms) && return "0.0"
    # (-a) + b is b - a exactly, so a leading subtraction moves behind the next term.
    length(terms) >= 2 && terms[1][1] && !terms[2][1] && ((terms[1], terms[2]) = (terms[2], terms[1]))
    length(terms) == 1 && return terms[1][1] ? "(-$(terms[1][2]))" : terms[1][2]
    io = IOBuffer()
    print(io, "(", terms[1][1] ? "-" : "", terms[1][2])
    for (neg, s) in terms[2:end]
        print(io, neg ? " - " : " + ", s)
    end
    print(io, ")")
    return String(take!(io))
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

"""    CLine(text, decls, always)

One statement of a generated function body, before pruning: `text` is the C (one or more
lines, without indentation), `decls` the local names it declares, `always` whether it is
kept regardless of use (the assignments to the outputs)."""
struct CLine
    text::String
    decls::Vector{String}
    always::Bool
end

const _LOCAL_READ = r"\b(?:o[0-9]+|p[0-9]+|d[0-9]+_[0-9]+|bg_mv[0-9]+|bg_lt[0-9]+)\b"
const _INTRINSIC_DECL = r"\bdouble (bg_(?:mv|lt)[0-9]+)\["

"""    _pending_line!(lines)

Move the intrinsic statements the last `cexpr` left pending (emit_intrinsics.jl: a local
array and the call that fills it) into `lines`, as one statement that declares them."""
function _pending_line!(lines::Vector{CLine})
    ctx = _intrinsic_context()
    (ctx === nothing || isempty(ctx.pending)) && return lines
    text = join(ctx.pending, "\n")
    empty!(ctx.pending)
    push!(lines, CLine(text, String[m.captures[1] for m in eachmatch(_INTRINSIC_DECL, text)], false))
    return lines
end

"""    _local_lines!(lines, exprs, obs, local_env, modes)

The observed locals `exprs` need, in observed order (each a common subexpression computed
once), with the intrinsic statements each one needs before it; `local_env` learns their
names."""
function _local_lines!(lines::Vector{CLine}, exprs, obs, local_env, modes)
    need = needed_observed(exprs, obs)
    for k in eachindex(obs.rhs)
        need[k] || continue
        cname = "o$(k - 1)"
        code = cexpr(obs.rhs[k], local_env, modes)
        _pending_line!(lines)
        push!(lines, CLine("const double $cname = $code; /* $(ccomment(obs.names[k])) */",
            [cname], false))
        local_env[obs.lhs[k]] = cname
    end
    return lines
end

"""    _print_used(io, lines)

Print the statements some kept statement reads, directly or through another kept one (a
backward pass: a statement reads only earlier ones). A variable that appears only in a
frozen switching condition is read through `m->c`, so its local would be unused (and fail
-Werror); a local array of an intrinsic that only such a local needs is dropped with it.
Comments carry signal names, so only the code before them is scanned for reads."""
function _print_used(io, lines::Vector{CLine})
    used = Set{String}()
    scan(s) = for l in split(s, '\n'), mm in eachmatch(_LOCAL_READ, first(split(l, "/*")))
        push!(used, mm.match)
    end
    keep = falses(length(lines))
    for i in length(lines):-1:1
        ln = lines[i]
        (ln.always || any(in(used), ln.decls)) || continue
        keep[i] = true
        scan(ln.text)
    end
    for (i, ln) in enumerate(lines)
        keep[i] || continue
        for l in split(ln.text, '\n')
            println(io, "    ", l)
        end
    end
end

"""    emit_function(io, signature, targets, env, obs; modes = nothing)

One C function: the observed locals the targets need (in observed order, so each is a
common subexpression computed once), then one `target = expr;` per `(target, expr, comment)`.
Locals nothing reads are left out (`_print_used`). The intrinsic calls' local arrays are
declared just before the first statement that needs them (emit_intrinsics.jl)."""
function emit_function(io, signature, targets, env, obs; modes = nothing)
    local_env = copy(env)
    lines = CLine[]
    begin_intrinsic_scope()
    _local_lines!(lines, Any[t[2] for t in targets], obs, local_env, modes)
    for (target, e, comment) in targets
        code = cexpr(e, local_env, modes)
        _pending_line!(lines)
        push!(lines, CLine("$target = $code;" * (comment === nothing ? "" : " /* $(ccomment(comment)) */"),
            String[], true))
    end
    end_intrinsic_scope()
    println(io, signature, " {")
    println(io, "    (void)m; (void)t; (void)x;")
    _print_used(io, lines)
    println(io, "}\n")
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

"""Whether `e` contains an unevaluated derivative: `Symbolics.derivative` of an opaque
registered function (an intrinsic of src/lower/fnmap.jl) has no rule and stays a
`Differential`, which has no C form."""
function _has_differential(e)
    e = Symbolics.unwrap(e)
    SymbolicUtils.iscall(e) || return false
    SymbolicUtils.operation(e) isa Symbolics.Differential && return true
    return any(_has_differential, SymbolicUtils.arguments(e))
end

"""    jacobian_c(rhs, xs, obs, env, modes; max_terms, max_seconds) -> NamedTuple

`bg_jacobian` (`J = ∂f/∂x`, only the structural non-zeros written) by forward accumulation
through the observed equations instead of differentiating the substituted right-hand side,
which blows up on multibody models. For every observed local `o_k` the derivatives
`∂o_k/∂x_j` become C locals, so each partial of each equation is computed once (common
subexpressions by construction):

    ∂o_k/∂x_j = Σ_v ∂rhs_k/∂v · ∂v/∂x_j      v a state or an earlier observed variable

Only the derivatives some row needs are emitted. Throws `JacobianTooBig` when the number of
terms exceeds `max_terms` or the build takes longer than `max_seconds`, and an `ExportError`
when a partial has no C form (an intrinsic without a symbolic derivative); the caller then
falls back to finite differences. Returns `(lines, jentries, terms, entries)`: the
statements before the entries, and every entry `(i, j, code)`. `render_jacobian` places
the entries once the layout of J is known (dense or the static sparse LU's)."""
function jacobian_c(rhs, xs, obs, env::Dict{Any,String}, modes; max_terms::Real = 200_000,
    max_seconds::Real = 120.0)
    t0 = time()
    guard() = time() - t0 > max_seconds &&
        throw(JacobianTooBig("the symbolic Jacobian took more than $(max_seconds) s"))
    nx = length(xs)
    nobs = length(obs.rhs)
    xidx = Dict{Any,Int}(x => i for (i, x) in enumerate(xs))
    relevant(v) = haskey(xidx, v) || haskey(obs.index, v)
    function partials(e, name)
        out = Tuple{Any,Any}[]
        e = Symbolics.unwrap(e)
        for v in Symbolics.get_variables(e)
            relevant(v) || continue
            # An opaque intrinsic has no rule: Symbolics leaves a `Differential`, or throws
            # outright when the call takes a table (an array argument).
            p = try
                Symbolics.unwrap(Symbolics.derivative(e, v))
            catch err
                err isa InterruptException && rethrow()
                throw(ExportError("`$name` calls a function without a symbolic derivative ($(first(sprint(showerror, err), 120)))"))
            end
            _has_differential(p) && throw(ExportError(
                "`$name` calls a function without a symbolic derivative"))
            _is_zero(p) || push!(out, (v, p))
        end
        guard()
        return out
    end
    need = needed_observed(rhs, obs)
    part_obs = Vector{Vector{Tuple{Any,Any}}}(undef, nobs)
    for k in 1:nobs
        part_obs[k] = need[k] ? partials(obs.rhs[k], obs.names[k]) : Tuple{Any,Any}[]
    end
    part_rhs = [partials(r, "the equation of row $i") for (i, r) in enumerate(rhs)]
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
    lines = CLine[]
    jentries = Tuple{Int,Int,String}[]
    terms = 0
    simplify = C_SIMPLIFY[]
    begin_intrinsic_scope()
    try
        local_env = copy(env)
        _local_lines!(lines, pexprs, obs, local_env, modes)
        D = Vector{Dict{Int,String}}(undef, nobs)
        nloc = 0
        function combine(pr)
            acc = Dict{Int,Vector{String}}()
            for (v, p) in pr
                src = haskey(xidx, v) ? Dict(xidx[v] => "1.0") : D[obs.index[v]]
                isempty(src) && continue
                pc = _is_one(p) ? "1.0" : cexpr(p, local_env, modes)
                _pending_line!(lines)
                if length(src) > 1 && !_simple_c(pc)
                    name = "p$(nloc)"
                    nloc += 1
                    push!(lines, CLine("const double $name = $pc;", [name], false))
                    pc = name
                end
                for (j, dj) in src
                    push!(get!(acc, j, String[]), pc == "1.0" ? dj : dj == "1.0" ? pc :
                        simplify && pc == "(-1.0)" ? "(-$dj)" : "$pc * $dj")
                end
                terms += length(src)
                terms > max_terms &&
                    throw(JacobianTooBig("the symbolic Jacobian needs more than $(round(Int, max_terms)) terms"))
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
                    push!(lines, CLine("const double $name = $(join(list, " + ")); /* d $(ccomment(obs.names[k])) / dx[$(j - 1)] */",
                        [name], false))
                    D[k][j] = name
                end
            end
        end
        for i in 1:nx
            acc = combine(part_rhs[i])
            for j in sort!(collect(keys(acc)))
                push!(jentries, (i, j, join(acc[j], " + ")))
            end
        end
    finally
        ctx = _intrinsic_context()
        ctx === nothing || empty!(ctx.pending)
        end_intrinsic_scope()
    end
    return (lines = lines, jentries = jentries, terms = terms, entries = length(jentries))
end

"""    render_jacobian(jc, targets) -> String

The body of the symbolic `bg_jacobian` from `jacobian_c`: entry `(i, j)` goes to
`J[targets[i, j]]` (`jacobian_targets`: row-major for the dense LU, the position in the
static sparse LU's value array otherwise). Locals no entry reads are left out."""
function render_jacobian(jc, targets::AbstractMatrix{<:Integer})
    lines = copy(jc.lines)
    for (i, j, code) in jc.jentries
        t = targets[i, j]
        t >= 0 || throw(ExportError("internal: the Jacobian entry ($i, $j) is outside the pattern"))
        push!(lines, CLine("J[$t] = $code;", String[], true))
    end
    io = IOBuffer()
    _print_used(io, lines)
    return String(take!(io))
end


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
