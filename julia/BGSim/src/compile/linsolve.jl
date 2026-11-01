# The linear solve `A \ b` on fixed-size arrays (spec "Built-in function whitelist": `\` via
# fixed-size LU).
#
# The language scalarizes every array at qualification (`QValue`), so a solve is unrolled into
# scalar expressions here, at compile time, like `A * x` and `transpose`. The factorisation is
# Doolittle's LU with **partial pivoting**, the algorithm of LAPACK `getrf`/`getrs`:
#
#   for k = 1 .. n-1
#       p      = the first row i >= k with the largest |A[i,k]|
#       swap rows k and p of A and of the right-hand side
#       l_i    = A[i,k] / A[k,k]                 (i > k)
#       A[i,j] = A[i,j] - l_i A[k,j]             (i > k, j > k, and every right-hand column)
#   x_n = y_n / U[n,n],  x_i = (y_i - sum_{j>i} U[i,j] x_j) / U[i,i]
#
# The pivot is chosen at run time, so the row swap is a selection: row `i` "wins" column `k`
# when `|A[i,k]|` beats the best of the rows before it (`c_i`, strictly greater, so a tie keeps
# the first row, as LAPACK's `idamax` does), and the pivot row is the last winner. The new
# pivot row is a chain of `ifelse(c_L, A[L,:], ifelse(c_{L-1}, ...))`, and a row that was the
# pivot receives the old row `k`.
#
# Every intermediate value is **spilled** through the context (`QCtx.spill`): a hidden
# algebraic unknown with one explicit equation in `@equations`, a local slot in `@discrete`.
# Without that, every factor would be copied into each later expression and the trees would
# grow exponentially with `n`. Entries that are literal numbers fold: a literal zero below the
# diagonal needs no elimination and takes no part in the pivot choice (a structurally
# triangular or block-diagonal matrix unrolls to its own short form), and an all-literal
# system is solved right away with Julia's `\`.
#
# A pivot change does not make the solution jump (it is the same `A^-1 b`), so the pivot
# conditions are no switching events: their equations carry `origin.kind === :solve`, which
# `nonsmooth_conditions` skips. The entries of `A` and `b` are spilled first with events
# kept, so an `abs(x)` inside `A` still gets its callback.

"""    _qsolve(q, A, B, r) -> Union{QValue,Nothing}

`A \\ B` for an `n×n` matrix `A` and an `n`-vector or `n×p` matrix `B`, unrolled as described
at the top of `linsolve.jl`. Reports E004 for a size mismatch, a structurally singular matrix
(a column whose entries are all literal zeros) and a context without slots (`@events`)."""
function _qsolve(q::QCtx, A::QValue, B::QValue, r::BGSim.SourceRange)
    if length(A.shape) != 2 || A.shape[1] != A.shape[2]
        _qreport!(
            q;
            code = "E004",
            message = isempty(A.shape) ?
                      "`a \\ B` with a scalar `a` is not defined; divide by the scalar instead" :
                      "`A \\ b` needs a square matrix `A`, got size $(A.shape)",
            range = r,
            hint = "write `A \\ b` with `A::Mat{n,n}` and `b::Vec{n}` or `B::Mat{n,p}`",
        )
        return nothing
    end
    n = A.shape[1]
    if isempty(B.shape) || B.shape[1] != n || length(B.shape) > 2
        _qreport!(
            q;
            code = "E004",
            message = "`A \\ b` with a $(n)x$(n) matrix needs a $n-vector or a $n-row matrix on the right, got $(isempty(B.shape) ? "a scalar" : "size $(B.shape)")",
            range = r,
        )
        return nothing
    end
    p = length(B.shape) == 1 ? 1 : B.shape[2]
    Ael(i, j) = _qpick(A, i, j)
    Bel(i, c) = length(B.shape) == 1 ? B.elems[i] : _qpick(B, i, c)

    # An all-literal system: Julia's own solve.
    if all(_num_lit, A.elems) && all(_num_lit, B.elems)
        Am = Float64[Float64(Ael(i, j).value) for i in 1:n, j in 1:n]
        Bm = Float64[Float64(Bel(i, c).value) for i in 1:n, c in 1:p]
        X = try
            Am \ Bm
        catch err
            err isa LinearAlgebra.SingularException || rethrow()
            _qreport!(q; code = "E004", message = "`A \\ b`: the constant matrix is singular",
                range = r)
            return nothing
        end
        elems = BGSim.Expr[Lit(X[i, c], r) for i in 1:n for c in 1:p]
        return QValue(B.shape, elems)
    end

    if q.spill === nothing
        _qreport!(
            q;
            code = "E004",
            message = "`A \\ b` on arrays is available in `@equations` and `@discrete`, not here",
            range = r,
            hint = "compute the solution in `@equations` or `@discrete` and use the result",
        )
        return nothing
    end
    keep(e) = q.spill(e, r, true)       # an input: its own nonsmooth calls stay events
    slot(e) = q.spill(e, r, false)      # a factor: its pivot conditions are no events

    # Working matrix: columns 1..n are A, columns n+1..n+p the right-hand sides.
    m = n + p
    W = Matrix{BGSim.Expr}(undef, n, m)
    for i in 1:n
        for j in 1:n
            W[i, j] = keep(Ael(i, j))
        end
        for c in 1:p
            W[i, n + c] = keep(Bel(i, c))
        end
    end

    for k in 1:(n - 1)
        rows = Int[i for i in k:n if !_zero_lit(W[i, k])]
        if isempty(rows)
            _singular_report!(q, k, r)
            return nothing
        end
        L = length(rows)
        if L == 1
            pr = rows[1]
            if pr != k
                # a static swap: only one row can be the pivot
                for j in k:m
                    W[pr, j], W[k, j] = W[k, j], W[pr, j]
                end
            end
            for j in (k + 1):m
                W[k, j] = slot(W[k, j])
            end
            continue
        end
        # The run-time pivot choice among `rows` (all with a non-literal-zero entry).
        conds = Vector{BGSim.Expr}(undef, L)   # conds[t] for t >= 2: rows[t] beats rows[1:t-1]
        best = slot(_abs_expr(W[rows[1], k], r))
        for t in 2:L
            a = slot(_abs_expr(W[rows[t], k], r))
            conds[t] = BGSim.Comparison(:>, a, best, r)
            t < L && (best = slot(IfElse(conds[t], a, best, r)))
        end
        # rows[t] is the pivot: conds[t] (t >= 2) and none of the later rows beat it.
        winner(t) = begin
            parts = BGSim.Expr[]
            t >= 2 && push!(parts, conds[t])
            for u in (t + 1):L
                push!(parts, UnOp(Symbol("!"), conds[u], r))
            end
            length(parts) == 1 ? parts[1] : BoolOp(Symbol("&&"), parts, r)
        end
        old_k = W[k, :]
        # the new pivot row: the last winner's row
        prow = Vector{BGSim.Expr}(undef, m)
        for j in k:m
            e = W[rows[1], j]
            for t in 2:L
                e = _select(conds[t], W[rows[t], j], e, r)
            end
            prow[j] = slot(e)
        end
        # a candidate row that won receives the old row `k`
        for t in 1:L
            i = rows[t]
            i == k && continue
            cond = winner(t)
            for j in k:m
                W[i, j] = _select(cond, old_k[j], W[i, j], r)
            end
        end
        # row k holds the pivot row (its own values when no other row won)
        for j in k:m
            W[k, j] = prow[j]
        end
        # elimination below the pivot
        for i in (k + 1):n
            (i in rows) || continue           # a literal zero below the pivot stays zero
            l = slot(_ldiv(W[i, k], W[k, k], r))
            W[i, k] = Lit(0.0, r)
            for j in (k + 1):m
                W[i, j] = slot(_lsub(W[i, j], _lmul(l, W[k, j], r), r))
            end
        end
    end
    _zero_lit(W[n, n]) && (_singular_report!(q, n, r); return nothing)

    # Back substitution, one right-hand column at a time.
    X = Matrix{BGSim.Expr}(undef, n, p)
    for c in 1:p
        for i in n:-1:1
            acc = W[i, n + c]
            for j in (i + 1):n
                acc = _lsub(acc, _lmul(W[i, j], X[j, c], r), r)
            end
            X[i, c] = slot(_ldiv(acc, W[i, i], r))
        end
    end
    elems = BGSim.Expr[X[i, c] for i in 1:n for c in 1:p]
    return QValue(B.shape, elems)
end

function _singular_report!(q::QCtx, k::Int, r)
    _qreport!(
        q;
        code = "E004",
        message = "`A \\ b`: the matrix is singular (column $k has only literal zeros on and below the diagonal)",
        range = r,
    )
    return nothing
end

_num_lit(e) = e isa Lit && e.value isa Real && !(e.value isa Bool)

_abs_expr(e::BGSim.Expr, r) =
    _num_lit(e) ? Lit(abs(Float64(e.value)), r) : Call(Name(:abs, r), BGSim.Expr[e], r)

# `ifelse(c, a, b)`, folded when both branches are the same atomic value.
function _select(c::BGSim.Expr, a::BGSim.Expr, b::BGSim.Expr, r)
    _same_atom(a, b) && return a
    return IfElse(c, a, b, r)
end

_same_atom(a::Name, b::Name) = a.name === b.name
_same_atom(a::Lit, b::Lit) = _num_lit(a) && _num_lit(b) && Float64(a.value) == Float64(b.value)
_same_atom(::Any, ::Any) = false

_is_one(e) = _num_lit(e) && Float64(e.value) == 1.0

function _lmul(a::BGSim.Expr, b::BGSim.Expr, r)
    (_zero_lit(a) || _zero_lit(b)) && return Lit(0.0, r)
    _num_lit(a) && _num_lit(b) && return Lit(Float64(a.value) * Float64(b.value), r)
    _is_one(a) && return b
    _is_one(b) && return a
    return BinOp(:*, a, b, r)
end

function _lsub(a::BGSim.Expr, b::BGSim.Expr, r)
    _zero_lit(b) && return a
    _num_lit(a) && _num_lit(b) && return Lit(Float64(a.value) - Float64(b.value), r)
    _zero_lit(a) && return UnOp(:-, b, r)
    return BinOp(:-, a, b, r)
end

function _ldiv(a::BGSim.Expr, b::BGSim.Expr, r)
    _zero_lit(a) && return Lit(0.0, r)
    _is_one(b) && return a
    _num_lit(a) && _num_lit(b) && return Lit(Float64(a.value) / Float64(b.value), r)
    return BinOp(:/, a, b, r)
end

"""    _equation_spill(b, st) -> Function

The `QCtx.spill` of `@equations`: a hidden algebraic unknown `<path>/__lu<k>` with the one
explicit equation `__lu<k> ~ expr`. It is not a declared signal, so it is not recorded, and
`mtkcompile` eliminates it into the observed equations (no state, no extra solve). The
instance's unknown and equation counts both grow by one, so the balance check is unchanged."""
function _equation_spill(b::Builder, st::BlockState)
    return function (e::BGSim.Expr, r, events::Bool)
        (e isa Name || e isa Lit) && return e
        st.var_count += 1
        id = _qname(st, Symbol("__lu", st.var_count))
        origin = Flat.Origin(; path = st.path, block = st.ref, node = st.node, range = r,
            kind = :block)
        _add_var!(
            b,
            Flat.FlatVar(id, :algebraic, :Real, nothing, nothing,
                Dict{Symbol,Any}(:hidden => true), origin),
        )
        name = Name(Symbol(id), r)
        push!(
            b.equations,
            Flat.FlatEq(
                name,
                e,
                Flat.Origin(; path = st.path, block = st.ref, node = st.node, range = r,
                    kind = events ? :block : :solve),
            ),
        )
        st.eq_count += 1
        return name
    end
end
