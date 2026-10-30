# Folded parameters substituted into the symbolic system, then simplified with cheap,
# predictable rules (plan/EXPORT_PLAN.md D-EX10).
#
# A folded parameter used to reach C only as a literal string (`env[p] = "0.0"`), so the
# expressions kept every `0.0 * x`, `1.0 * x` and `x + 0.0` of the model's constant axes,
# offsets and unit gains. gcc -O2 without -ffast-math may not remove them (`0.0 * x` is NaN
# for an infinite `x`, `x + 0.0` is not `x` for `x = -0.0`), and the Jacobian's structural
# pattern counted them as non-zeros, which enlarged the static sparse LU.
#
# `fold_simplify` substitutes the folded values and rebuilds bottom-up, once per distinct
# subexpression (memoized):
#
#   * a call whose arguments are all numbers is evaluated (arithmetic, comparisons, logic
#     and the elementary functions with a C twin of the same semantics; never `round`, an
#     intrinsic or anything unknown);
#   * `+`, `*`, `/` and `^` are rebuilt through SymbolicUtils, which already normalizes
#     `0 * x -> 0`, `1 * x -> x`, `x + 0 -> x`, `x^1 -> x`, `x / 1 -> x`, merges numeric
#     coefficients and drops empty terms;
#   * `ifelse(c, a, b)` with a constant `c` is its branch, and `ifelse(c, a, a)` is `a`;
#     `&`/`|` with a constant operand reduce.
#
# No full `simplify`: it is unpredictable in time and form on multibody expressions. Tables
# (`array_literal` arguments of the intrinsics) are left as they are; their folded elements
# still become literals through `env`.
#
# The semantic difference is accepted and documented: `0 * x -> 0` drops the NaN of an
# infinite or NaN `x`, and `x + 0 -> x` keeps the sign of a negative zero.

"""Operations `fold_simplify` evaluates when every argument is a number. Their Julia
definitions match the C runtime's (`bg_runtime.h`); `round` is left out (the C twin rounds
half away from zero)."""
const _FOLDABLE = Set{Any}([+, -, *, /, ^, ifelse, (&), (|), (!), atan, min, max, hypot,
    mod, rem, sin, cos, tan, asin, acos, sinh, cosh, tanh, exp, log, log10, sqrt, abs,
    floor, ceil, sign, (>=), (>), (<=), (<), (==), (!=)])

_is_logic(op) = op === (&) || op === (|) || op === (!)
_is_cmp(op) = haskey(C_CMP, op)

# A number as the C code computes it: every arithmetic value is a double.
_as_double(v::Bool) = v
_as_double(v::Real) = Float64(v)

"""    _fold_call(op, vals) -> Number or nothing

`op(vals...)` on numbers, in double precision for arithmetic (as in C); `nothing` when the
operation is not foldable or Julia throws (a domain error stays for C to evaluate)."""
function _fold_call(op, vals)
    op in _FOLDABLE || return nothing
    all(v -> v isa Real, vals) || return nothing
    try
        r = if _is_logic(op)
            op(map(v -> v isa Bool ? v : !iszero(v), vals)...)
        elseif op === ifelse
            (vals[1] isa Bool ? vals[1] : !iszero(vals[1])) ? _as_double(vals[2]) : _as_double(vals[3])
        else
            op(map(v -> v isa Bool ? Float64(v) : Float64(v), vals)...)
        end
        r isa Real || return nothing
        return r isa Bool ? r : Float64(r)
    catch err
        err isa InterruptException && rethrow()
        return nothing
    end
end

_truth(c) = c isa Bool ? c : !iszero(c)

"""    fold_simplify(e, subs, memo) -> symbolic or Number

`e` with every key of `subs` (a folded parameter, or an observed variable already known to be
constant) replaced by its value, simplified bottom-up (file header). `memo` maps each visited
subexpression to its result. A result that is a constant is returned as a number."""
function fold_simplify(e, subs::AbstractDict, memo::IdDict{Any,Any})
    e = Symbolics.unwrap(e)
    e isa Number && return e
    r = get(memo, e, memo)
    r === memo || return r
    r = _fold_simplify(e, subs, memo)
    memo[e] = r
    return r
end

function _fold_simplify(e, subs, memo)
    v = get(subs, e, nothing)
    v === nothing || return v
    c = _try_const(e)
    c === nothing || return c
    SymbolicUtils.iscall(e) || return e
    op = SymbolicUtils.operation(e)
    # Atoms with a call form: a variable `x(t)`, an array element, an unevaluated derivative,
    # a table.
    (op isa SymbolicUtils.BasicSymbolic || op === getindex || op isa Symbolics.Differential ||
     _is_array_literal(e)) && return e
    args = SymbolicUtils.arguments(e)
    intrinsic = _bgsim_fn(op) !== nothing
    new = Vector{Any}(undef, length(args))
    changed = false
    for (k, a) in enumerate(args)
        a = Symbolics.unwrap(a)
        n = intrinsic && _is_array_literal(a) ? a : fold_simplify(a, subs, memo)
        new[k] = n
        changed |= n !== a
    end
    intrinsic && return changed ? _rebuild(e, op, new) : e
    vals = Any[_try_const(n) for n in new]
    if all(v -> v !== nothing, vals)
        f = _fold_call(op, vals)
        f === nothing || return f
    end
    if op === ifelse
        cv = vals[1]
        cv isa Real && return _truth(cv) ? new[2] : new[3]
        isequal(new[2], new[3]) && return new[2]
    elseif op === (&) || op === (|)
        absorbing = op === (|)       # true | x == true, false & x == false
        rest = Any[]
        for (n, v) in zip(new, vals)
            if v isa Real
                _truth(v) == absorbing && return absorbing
            else
                push!(rest, n)
            end
        end
        isempty(rest) && return !absorbing
        length(rest) == 1 && return rest[1]
        if length(rest) < length(new)
            new = rest
            changed = true
        end
    end
    changed || return e
    r = _rebuild(e, op, new)
    c = _try_const(r)
    return c === nothing ? r : c
end

_rebuild(e, op, args) = Symbolics.unwrap(SymbolicUtils.maketerm(typeof(e), op, args,
    SymbolicUtils.metadata(e)))

"""    as_symbolic(r) -> symbolic

A `fold_simplify` result in the form the rest of the export expects: a number becomes a
SymbolicUtils constant."""
as_symbolic(r) = r isa Number ? Symbolics.unwrap(Symbolics.Num(r)) : r

"""    simplify_system!(subs, rhs, obs, extra) -> NamedTuple

Substitute `subs` (folded parameter => value) into the right-hand side `rhs`, the observed
right-hand sides `obs.rhs` (in place, in their topological order: an observed variable that
becomes a constant is substituted into everything after it) and every expression vector in
`extra`, and simplify (`fold_simplify`). Returns the number of observed variables that became
constants and the seconds spent."""
function simplify_system!(subs::AbstractDict, rhs::AbstractVector, obs, extra = ())
    t0 = time()
    s = Dict{Any,Any}(subs)
    memo = IdDict{Any,Any}()
    nconst = 0
    for k in eachindex(obs.rhs)
        r = fold_simplify(obs.rhs[k], s, memo)
        if r isa Number
            s[obs.lhs[k]] = r
            nconst += 1
        end
        obs.rhs[k] = as_symbolic(r)
    end
    # The memo stays valid: a subexpression that reads observed variable k only occurs after
    # equation k, by when its constant (if any) is in `s`.
    for i in eachindex(rhs)
        rhs[i] = as_symbolic(fold_simplify(rhs[i], s, memo))
    end
    for v in extra
        for i in eachindex(v)
            v[i] = as_symbolic(fold_simplify(v[i], s, memo))
        end
    end
    return (constant_observed = nconst, seconds = time() - t0)
end
