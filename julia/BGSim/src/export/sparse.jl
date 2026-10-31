# Sparse Jacobian, static sparse LU and the coloured finite-difference Jacobian
# (plan/EXPORT_PLAN.md D-EX12, D-EX13, work package J-EX4).
#
# A Rosenbrock step solves with W = M - hγ·J. Everything about the sparsity of W is decided
# here, at export, so the C code does a fixed amount of work in a fixed order:
#
#   pattern     `jacobian_pattern`: S[i, j] when d/dt x_i can depend on x_j. It follows the
#               variables of the right-hand side through the observed equations, so it is the
#               structure, not the numeric zeros of one point (those can be accidental).
#   matching    `row_matching`: a static row permutation that puts a structural non-zero on
#               every pivot. A differential row keeps its own diagonal (its mass); the
#               algebraic rows of a DAE (mass 0) are matched to the algebraic unknowns
#               through ∂g/∂z, which an index-1 DAE has structurally non-singular, but whose
#               diagonal can be structurally zero (the k-th algebraic equation sits in the
#               row of the k-th algebraic unknown, an arbitrary pairing). The matching is a
#               maximum-product assignment on the scanned Jacobians (MC64-like), or a
#               structural maximum matching without them. It is used only when the identity
#               fails: a structurally zero diagonal, or a failed pivot check.
#   ordering    `minimum_degree_order`: a fill-reducing symmetric permutation of the pattern
#               of the row-matched W (exact minimum degree on B + Bᵀ, ties to the lowest
#               index).
#   factors     `static_lu`: the symbolic LU of Pr·W·Pcᵀ with no pivoting (Pr = Pc without a
#               matching). The fill-in, the row-compressed layout and every multiply-add are
#               fixed; C runs them from static index tables (`emit_sparse_lu`).
#   colouring   `colour_columns`: a greedy distance-2 colouring of the columns of S. Columns
#               of one colour share no row, so one derivative call per colour gives all their
#               Jacobian entries (`emit_fd_jacobian`, the D-EX12 fallback).
#
# Static pivoting. The pivots are the diagonal of Pr·W·Pcᵀ in a fixed order, so a step never
# searches for a pivot or moves a row. For an ODE this is safe when W is diagonally
# dominant, which holds for small hγ (W → M = I), and when the symmetric part of W is
# positive definite, which holds when J is dissipative (J + Jᵀ ≤ 0): every pivot is then at
# least 1. An algebraic row of a DAE has mass 0, so its pivot comes from J alone and small
# hγ does not help: the row matching gives it a structurally non-zero pivot in ∂g/∂z (the
# algebraic block of W is -hγ·∂g/∂z, and the updates from differential rows are O(h²γ²)).
# Neither is guaranteed in general, so (a) `bg_w_factor` checks every
# pivot against the largest entry of its row and returns an error status on a tiny or non-finite one, and (b) the export
# factors W at the scanned points and reports the smallest pivot ratio, the growth and the
# residual against a pivoted dense solve (`static_lu_check`); a failed check falls back to
# the dense LU with partial pivoting (W211).

"""    jacobian_pattern(rhs, obs, xs) -> BitMatrix

The structural pattern of ∂rhs/∂x: `S[i, j]` is true when `rhs[i]` reads `xs[j]`, directly
or through the observed equations (which are topologically ordered)."""
function jacobian_pattern(rhs, obs, xs)
    nx = length(xs)
    xidx = Dict{Any,Int}()
    for (j, x) in enumerate(xs)
        xidx[Symbolics.unwrap(x)] = j
    end
    deps = Vector{BitSet}(undef, length(obs.rhs))
    function depset(e)
        s = BitSet()
        for v in Symbolics.get_variables(Symbolics.unwrap(e))
            v = Symbolics.unwrap(v)
            j = get(xidx, v, 0)
            if j > 0
                push!(s, j)
                continue
            end
            k = get(obs.index, v, 0)
            k == 0 && continue
            isassigned(deps, k) ||
                throw(ExportError("the observed equation of `$(obs.names[k])` is used before it is defined"))
            union!(s, deps[k])
        end
        return s
    end
    for k in eachindex(obs.rhs)
        deps[k] = depset(obs.rhs[k])
    end
    S = falses(nx, nx)
    for i in 1:nx
        for j in depset(rhs[i])
            S[i, j] = true
        end
    end
    return S
end

"""    colour_columns(S) -> Vector{Int}

A greedy distance-2 colouring of the columns of `S` (colours 1, 2, ...): two columns that
have a non-zero in the same row never share a colour. Columns are visited by decreasing
count of non-zeros, ties by index, so the result is deterministic."""
function colour_columns(S::AbstractMatrix{Bool})
    nr, nc = size(S)
    rows_of = [findall(view(S, :, j)) for j in 1:nc]
    cols_of = [findall(view(S, i, :)) for i in 1:nr]
    order = sort(1:nc; by = j -> (-length(rows_of[j]), j))
    colour = zeros(Int, nc)
    banned = zeros(Int, nc + 1)    # banned[c] == j: colour c is taken next to column j
    for j in order
        for i in rows_of[j], k in cols_of[i]
            colour[k] > 0 && (banned[colour[k]] = j)
        end
        c = 1
        while banned[c] == j
            c += 1
        end
        colour[j] = c
    end
    return colour
end

"""    colouring_valid(S, colour) -> Bool

True when no row of `S` has two non-zeros in columns of the same colour."""
function colouring_valid(S::AbstractMatrix{Bool}, colour::AbstractVector{<:Integer})
    length(colour) == size(S, 2) || return false
    all(>(0), colour) || return false
    for i in 1:size(S, 1)
        seen = Set{Int}()
        for j in findall(view(S, i, :))
            colour[j] in seen && return false
            push!(seen, colour[j])
        end
    end
    return true
end

"""    structural_matching(P) -> Vector{Int}

A maximum bipartite matching of the rows and columns of the square pattern `P`: `m[j]` is
the row matched to column `j`, 0 when the pattern is structurally singular and column `j`
stays unmatched. The diagonal is matched first wherever it is structural, then each
unmatched column, in index order, searches an augmenting path (rows in index order), so the
result is deterministic and keeps a row in place whenever it can."""
function structural_matching(P::AbstractMatrix{Bool})
    n = size(P, 1)
    size(P, 2) == n || throw(ArgumentError("the pattern is not square"))
    rows_of = [findall(view(P, :, j)) for j in 1:n]
    m = zeros(Int, n)        # m[j]: row of column j
    r = zeros(Int, n)        # r[i]: column of row i
    for j in 1:n
        P[j, j] && (m[j] = j; r[j] = j)
    end
    seen = falses(n)
    function augment(j)
        for i in rows_of[j]
            seen[i] && continue
            seen[i] = true
            if r[i] == 0 || augment(r[i])
                m[j] = i
                r[i] = j
                return true
            end
        end
        return false
    end
    for j in 1:n
        m[j] == 0 || continue
        fill!(seen, false)
        augment(j)
    end
    return m
end

"""    _assignment(C) -> Vector{Int}

The minimum-cost perfect assignment of the finite square cost matrix `C` (Hungarian
algorithm with potentials, O(n³)): `m[j]` is the row assigned to column `j`. Rows are added
in index order and every comparison is strict, so ties resolve deterministically."""
function _assignment(C::AbstractMatrix{Float64})
    n = size(C, 1)
    u = zeros(n + 1)               # row potentials, index i + 1 (0 is the virtual row)
    v = zeros(n + 1)               # column potentials, index j + 1
    p = zeros(Int, n + 1)          # p[j + 1]: the row assigned to column j
    way = zeros(Int, n + 1)
    minv = zeros(n + 1)
    used = falses(n + 1)
    for i in 1:n
        p[1] = i
        j0 = 0
        fill!(minv, Inf)
        fill!(used, false)
        while true
            used[j0 + 1] = true
            i0 = p[j0 + 1]
            delta, j1 = Inf, 0
            for j in 1:n
                used[j + 1] && continue
                cur = C[i0, j] - u[i0 + 1] - v[j + 1]
                if cur < minv[j + 1]
                    minv[j + 1] = cur
                    way[j + 1] = j0
                end
                if minv[j + 1] < delta
                    delta, j1 = minv[j + 1], j
                end
            end
            for j in 0:n
                if used[j + 1]
                    u[p[j + 1] + 1] += delta
                    v[j + 1] -= delta
                else
                    minv[j + 1] -= delta
                end
            end
            j0 = j1
            p[j0 + 1] == 0 && break
        end
        while j0 != 0
            j1 = way[j0 + 1]
            p[j0 + 1] = p[j1 + 1]
            j0 = j1
        end
    end
    return p[2:end]
end

"""    row_matching(S, mass; Js = ()) -> NamedTuple

A static row permutation of W = M - hγ·J (pattern `S` of J, diagonal `mass`) that puts a
structural non-zero on every pivot: `rowmatch[j]` is the row of W whose pivot is in column
`j`. A row with mass keeps its own diagonal. The algebraic rows (mass 0) are assigned to
the algebraic columns on the pattern of ∂g/∂z:

  * with Jacobians `Js` (in the rows of the C code, the scanned points), the assignment
    maximises the product over the pivots of the worst relative size
    `w_ij = min over Js of |J_ij| / max_k |J_ik|` (MC64's objective with the row scaling; an
    algebraic row of W is -hγ times the row of J, so hγ cancels). A structural entry that
    is zero at some point costs more than any non-zero one, an entry outside the pattern
    more than any structural one. Ties keep a row on its own diagonal;
  * without, a structural maximum matching (`structural_matching`).

Returns `rowmatch`, `complete` (every pivot structural), `weighted` and `permuted` (rows not
on their own diagonal)."""
function row_matching(S::AbstractMatrix{Bool}, mass::AbstractVector; Js = ())
    n = size(S, 1)
    rowmatch = collect(1:n)
    alg = findall(iszero, mass)
    na = length(alg)
    weighted = false
    complete = true
    if na > 0
        A = S[alg, alg]
        Jv = [J for J in Js if all(isfinite, J)]
        local m
        if isempty(Jv)
            m = structural_matching(A)
        else
            weighted = true
            w = fill(Inf, na, na)
            for J in Jv
                for (a, i) in enumerate(alg)
                    s = maximum(abs, view(J, i, :); init = 0.0)
                    for (b, j) in enumerate(alg)
                        A[a, b] || continue
                        w[a, b] = min(w[a, b], s > 0 ? abs(J[i, j]) / s : 0.0)
                    end
                end
            end
            finite_costs = [-log(w[a, b]) for b in 1:na for a in 1:na if A[a, b] && w[a, b] > 0]
            big = (na + 1) * (maximum(finite_costs; init = 0.0) + 1.0)
            huge = (na + 1) * (big + 1.0)
            C = Matrix{Float64}(undef, na, na)
            for b in 1:na, a in 1:na
                C[a, b] = !A[a, b] ? huge : w[a, b] > 0 ? -log(w[a, b]) : big
            end
            for a in 1:na
                C[a, a] -= 1.0e-9           # a tie keeps the row on its own diagonal
            end
            m = _assignment(C)
            all(A[m[b], b] for b in 1:na) || (m = structural_matching(A))
        end
        complete = all(>(0), m)
        if !complete
            # structurally singular ∂g/∂z (not index 1): pair the rest in order; the pivot
            # check then fails
            free = setdiff(1:na, m)
            for b in 1:na
                m[b] == 0 && (m[b] = popfirst!(free))
            end
        end
        for b in 1:na
            rowmatch[alg[b]] = alg[m[b]]
        end
    end
    return (rowmatch = rowmatch, complete = complete, weighted = weighted,
        permuted = count(j -> rowmatch[j] != j, 1:n))
end

_row_matched(S::AbstractMatrix{Bool}, rowmatch::Vector{Int}) = S[rowmatch, :]

"""    minimum_degree_order(S) -> Vector{Int}

A fill-reducing elimination order of the symmetric pattern `S + Sᵀ`: repeatedly the vertex
of the elimination graph with the fewest neighbours (ties to the lowest index), whose
neighbours then become a clique. Exact minimum degree; at export sizes (a few hundred
states) this costs milliseconds and needs no external ordering library."""
function minimum_degree_order(S::AbstractMatrix{Bool})
    n = size(S, 1)
    adj = [BitSet() for _ in 1:n]
    for j in 1:n, i in 1:n
        i != j && (S[i, j] || S[j, i]) && push!(adj[i], j)
    end
    alive = trues(n)
    order = Int[]
    for _ in 1:n
        best, degree = 0, typemax(Int)
        for v in 1:n
            alive[v] || continue
            d = length(adj[v])
            d < degree && ((best, degree) = (v, d))
        end
        nb = collect(adj[best])
        for u in nb
            delete!(adj[u], best)
            for w in nb
                w != u && push!(adj[u], w)
            end
        end
        alive[best] = false
        empty!(adj[best])
        push!(order, best)
    end
    return order
end

"""    StaticLU

The symbolic LU of `Pr·W·Pcᵀ` without pivoting (1-based; the C tables are the same minus 1).
Row `k` of the factored matrix is row `rperm[k]` of W, column `k` is column `perm[k]`; the
two are equal unless a row matching (`row_matching`) moved algebraic rows.

| field | meaning |
| --- | --- |
| `perm` | `perm[k]` is the state (column of W, unknown of the solve) of pivot `k` |
| `rperm` | `rperm[k]` is the row of W (equation) of pivot `k` |
| `rowptr`, `col` | the filled pattern, row-compressed with sorted columns: row `k` holds L (columns `< k`), the pivot, then U |
| `diag` | position of the pivot of row `k` |
| `upd` | the destination of every multiply-add `a[upd[u]] -= l·a[q]`, in factorization order |
| `nnz_w` | non-zeros of the pattern of the permuted W before fill (J plus the pivots) |
"""
struct StaticLU
    n::Int
    perm::Vector{Int}
    rperm::Vector{Int}
    rowptr::Vector{Int}
    col::Vector{Int}
    diag::Vector{Int}
    upd::Vector{Int}
    nnz_w::Int
end

lu_nnz(lu::StaticLU) = length(lu.col)
lu_fill(lu::StaticLU) = lu_nnz(lu) - lu.nnz_w
lu_nl(lu::StaticLU) = sum(lu.diag[k] - lu.rowptr[k] for k in 1:lu.n; init = 0)
"""Floating-point operations of one factorization: a multiply per L entry, two per update,
a division per pivot (the pivot check and forming W are not counted)."""
lu_flops(lu::StaticLU) = lu_nl(lu) + 2 * length(lu.upd) + lu.n
"""Floating-point operations of one solve (forward and backward substitution)."""
lu_solve_flops(lu::StaticLU) = 2 * (lu_nnz(lu) - lu.n) + lu.n

"""    static_lu(S; rowmatch = 1:n, order = minimum_degree_order(S[rowmatch, :])) -> StaticLU

The symbolic factorization of the pattern `S` with its rows matched to the pivots
(`rowmatch[j]` is the row whose pivot is in column `j`, see `row_matching`), symmetrically
permuted by `order`, plus the pivots. Without a matching this is `S ∪ I` permuted by
`order`."""
function static_lu(S::AbstractMatrix{Bool}; rowmatch::Vector{Int} = collect(1:size(S, 1)),
    order::Vector{Int} = minimum_degree_order(_row_matched(S, rowmatch)))
    n = size(S, 1)
    sort(order) == collect(1:n) || throw(ArgumentError("`order` is not a permutation of 1:$n"))
    sort(rowmatch) == collect(1:n) ||
        throw(ArgumentError("`rowmatch` is not a permutation of 1:$n"))
    rperm = rowmatch[order]
    B = falses(n, n)
    for j in 1:n, i in 1:n
        B[i, j] = S[rperm[i], order[j]] || i == j
    end
    rows = Vector{Vector{Int}}(undef, n)
    mark = falses(n)
    for i in 1:n
        mark .= view(B, i, :)
        # Eliminate with every earlier row whose column is (or becomes) non-zero in row i;
        # elimination with row k only adds columns > k, so one ascending sweep sees them all.
        k = findnext(mark, 1)
        while k !== nothing && k < i
            for j in rows[k]
                j > k && (mark[j] = true)
            end
            k = findnext(mark, k + 1)
        end
        rows[i] = findall(mark)
    end
    rowptr = Vector{Int}(undef, n + 1)
    rowptr[1] = 1
    for i in 1:n
        rowptr[i + 1] = rowptr[i] + length(rows[i])
    end
    col = reduce(vcat, rows; init = Int[])
    diag = [rowptr[i] - 1 + findfirst(==(i), rows[i]) for i in 1:n]
    upd = Int[]
    where_ = zeros(Int, n)
    for i in 1:n
        for p in rowptr[i]:rowptr[i + 1] - 1
            where_[col[p]] = p
        end
        for p in rowptr[i]:diag[i] - 1
            k = col[p]
            for q in diag[k] + 1:rowptr[k + 1] - 1
                push!(upd, where_[col[q]])
            end
        end
    end
    return StaticLU(n, copy(order), rperm, rowptr, col, diag, upd, count(B))
end

"""    lu_rows_permuted(lu) -> Int

The rows of W whose pivot is not their own diagonal (0 without a row matching)."""
lu_rows_permuted(lu::StaticLU) = count(k -> lu.rperm[k] != lu.perm[k], 1:lu.n)

"""    lu_position(lu, i, j, ip = invperm(lu.perm), ipr = invperm(lu.rperm)) -> Int

The position of the entry `(i, j)` of W (row `i`, the equation of state row `i`; column `j`,
state `j`) in the value array, or 0 when it is outside the pattern."""
function lu_position(lu::StaticLU, i::Int, j::Int, ip::Vector{Int} = invperm(lu.perm),
    ipr::Vector{Int} = invperm(lu.rperm))
    r, c = ipr[i], ip[j]
    for p in lu.rowptr[r]:lu.rowptr[r + 1] - 1
        lu.col[p] == c && return p
    end
    return 0
end

"""    lu_mass_positions(lu, mass = ones(n)) -> Vector{Int}

The position in the value array where `bg_w_factor` adds `mass[i]` (the entry `(i, i)` of
W). A row with mass always has its diagonal in the pattern; an algebraic row (mass 0)
whose diagonal is not in the pattern gets the pivot of its row, where adding 0 is a
no-op."""
function lu_mass_positions(lu::StaticLU, mass::AbstractVector = ones(lu.n))
    ip, ipr = invperm(lu.perm), invperm(lu.rperm)
    pos = zeros(Int, lu.n)
    for i in 1:lu.n
        p = lu_position(lu, i, i, ip, ipr)
        if p == 0
            iszero(mass[i]) ||
                throw(ExportError("internal: the mass of state $i is outside the LU pattern"))
            p = lu.diag[ipr[i]]
        end
        pos[i] = p
    end
    return pos
end

"""    lu_values(lu, W) -> Vector{Float64}

The entries of the dense matrix `W` on the value layout of `lu` (fill positions zero)."""
function lu_values(lu::StaticLU, W::AbstractMatrix)
    a = zeros(lu_nnz(lu))
    for r in 1:lu.n, p in lu.rowptr[r]:lu.rowptr[r + 1] - 1
        a[p] = W[lu.rperm[r], lu.perm[lu.col[p]]]
    end
    return a
end

"""The pivot test of `bg_w_factor`: a pivot must exceed this fraction of its row's largest
entry (taken before the row is eliminated)."""
const LU_TINY = 1.0e-12

"""    lu_factor!(a, lu, inv) -> Bool

The numeric factorization on the static pattern, exactly as the generated C does it
(`bg_w_factor`): `a` holds W on the layout of `lu` and is overwritten by L (unit diagonal,
multipliers) and U; `inv` receives 1 / pivot. False on a tiny or non-finite pivot."""
function lu_factor!(a::Vector{Float64}, lu::StaticLU, inv::Vector{Float64})
    u = 1
    for i in 1:lu.n
        s = 0.0
        for p in lu.rowptr[i]:lu.rowptr[i + 1] - 1
            s = max(s, abs(a[p]))
        end
        for p in lu.rowptr[i]:lu.diag[i] - 1
            k = lu.col[p]
            l = a[p] * inv[k]
            a[p] = l
            for q in lu.diag[k] + 1:lu.rowptr[k + 1] - 1
                a[lu.upd[u]] -= l * a[q]
                u += 1
            end
        end
        d = a[lu.diag[i]]
        abs(d) > LU_TINY * s || return false
        inv[i] = 1.0 / d
    end
    return true
end

"""    lu_solve!(b, a, lu, inv, y)

Solve `W x = b` in place with the factors from `lu_factor!` (`bg_w_solve`)."""
function lu_solve!(b::AbstractVector{Float64}, a::Vector{Float64}, lu::StaticLU,
    inv::Vector{Float64}, y::Vector{Float64} = zeros(lu.n))
    for k in 1:lu.n
        s = b[lu.rperm[k]]
        for p in lu.rowptr[k]:lu.diag[k] - 1
            s -= a[p] * y[lu.col[p]]
        end
        y[k] = s
    end
    for k in lu.n:-1:1
        s = y[k]
        for p in lu.diag[k] + 1:lu.rowptr[k + 1] - 1
            s -= a[p] * y[lu.col[p]]
        end
        y[k] = s * inv[k]
    end
    for k in 1:lu.n
        b[lu.perm[k]] = y[k]
    end
    return b
end

"""The largest componentwise backward error (Oettli-Prager) of a static-LU solve that the
pivot check accepts: the solve must be exact for a W perturbed by at most this fraction of
each entry (and of b)."""
const LU_BACKWARD_ERROR = 1.0e-10

"""    static_lu_check(lu, Js, hg; mass = ones(n)) -> NamedTuple

Factor `W = M - hg·J` (`M = diag(mass)`; an algebraic row has mass 0, so its pivot comes
from J alone) for every Jacobian in `Js` with the static pivots and report the smallest
pivot ratio |u_kk| / (largest entry of its row of W), the growth (largest entry of the
factors over the largest entry of W), the componentwise backward error of a solve
(`backward_error`) and its relative difference to a pivoted dense solve (`residual`, for
information). `ok` is false when a factorization failed or the backward error is above
`LU_BACKWARD_ERROR`.

The backward error, not the difference to the dense solve, decides: it is invariant to the
row scaling, and a DAE's W is badly row-scaled (differential rows O(1), algebraic rows
O(hγ|J|)). Partial pivoting then picks its pivots from the differential rows, and the
dense solve is the less accurate of the two: on the rigid-joint RRR arm (cond(W) 1e10, 3e3
after row scaling) the static LU's backward error is 2e-16 at every point and LAPACK's up
to 6e-8, so their difference reached 6e-9, close to the old 1e-8 limit, through no fault
of the static LU."""
static_lu_check(lu::StaticLU, Js, hg::Float64; mass::AbstractVector = ones(lu.n)) =
    _lu_check(lu, (Matrix{Float64}(LinearAlgebra.Diagonal(Float64.(mass))) .- hg .* J
                   for J in Js if all(isfinite, J)))

"""    projection_matrix(J, mass) -> Matrix{Float64}

The matrix of `bg_project`'s Newton step on 0 = g(x_d, z) with the differential states held:
a row with mass is the identity row, an algebraic row is its row of J. Solving it with the
right-hand side -g on the algebraic rows (0 elsewhere) gives Δx_d = 0 and ∂g/∂z Δz = -g. Its
pattern is inside W's, so the static LU's tables factor it; elimination with the identity
rows changes nothing, so the static pivots are those of ∂g/∂z in the matched order."""
function projection_matrix(J::AbstractMatrix, mass::AbstractVector)
    n = size(J, 1)
    A = zeros(n, n)
    for i in 1:n
        if iszero(mass[i])
            A[i, :] .= view(J, i, :)
        else
            A[i, i] = 1.0
        end
    end
    return A
end

"""    projection_check(lu, Js, mass) -> NamedTuple

`static_lu_check`'s test for the projection matrix (`projection_matrix`) at every Jacobian
in `Js`: when it passes, `bg_project` factors ∂g/∂z on the static tables instead of a dense
Gaussian elimination of the algebraic block."""
projection_check(lu::StaticLU, Js, mass::AbstractVector) =
    _lu_check(lu, (projection_matrix(J, mass) for J in Js if all(isfinite, J)))

function _lu_check(lu::StaticLU, Ws)
    n = lu.n
    min_ratio, growth, residual, berr, points = Inf, 0.0, 0.0, 0.0, 0
    ok = true
    for W in Ws
        a = lu_values(lu, W)
        rowmax = zeros(n)
        for r in 1:n, p in lu.rowptr[r]:lu.rowptr[r + 1] - 1
            rowmax[r] = max(rowmax[r], abs(a[p]))
        end
        wmax = maximum(abs, a)
        inv = zeros(n)
        points += 1
        if !lu_factor!(a, lu, inv)
            ok = false
            min_ratio = 0.0
            continue
        end
        for r in 1:n
            min_ratio = min(min_ratio, abs(a[lu.diag[r]]) / max(rowmax[r], floatmin()))
        end
        growth = max(growth, maximum(abs, a) / max(wmax, floatmin()))
        b = [1.0 + (k - 1) / max(n - 1, 1) for k in 1:n]    # 1 .. 2 (n = 1 included)
        x = lu_solve!(copy(b), a, lu, inv)
        all(isfinite, x) || (ok = false; berr = Inf; continue)
        # Oettli-Prager: x solves (W + ΔW) x = b + Δb exactly with |ΔW| <= ω|W|, |Δb| <= ω|b|
        r = abs.(b .- W * x)
        s = abs.(W) * abs.(x) .+ abs.(b)
        berr = max(berr, maximum(i -> r[i] == 0 ? 0.0 : r[i] / s[i], 1:n; init = 0.0))
        xd = W \ b
        residual = max(residual, maximum(abs, x .- xd) / max(maximum(abs, xd), floatmin()))
    end
    berr > LU_BACKWARD_ERROR && (ok = false)
    return (ok = ok, points = points, min_pivot_ratio = isfinite(min_ratio) ? min_ratio : 1.0,
        growth = growth, residual = residual, backward_error = berr)
end

# ---------------------------------------------------------------------------------------
# C emission

# bg_project's Newton matrix on the static tables (`projection_matrix`), factored in m->lu:
# bg_project runs between steps, and every step forms and factors W again.
const _ALG_FACTOR_C = """

    /* The Newton matrix of bg_project (BG_SPARSE_PROJECT): identity rows for the states with
       mass, the rows of J for the algebraic equations, factored on the same static tables
       (in m->lu, which the next step overwrites). Elimination with the identity rows changes
       nothing, so the pivots are those of dg/dz in the matched order. */
    int bg_alg_factor(bg_model *m) {
        double *a = m->lu;
        for (int k = 0; k < BG_NX; ++k) {
            const int alg = bg_mass[bg_lu_rperm[k]] == 0.0;
            for (int p = bg_lu_rowptr[k]; p < bg_lu_rowptr[k + 1]; ++p) a[p] = alg ? m->jac[p] : 0.0;
        }
        for (int i = 0; i < BG_NX; ++i)
            if (bg_mass[i] != 0.0) a[bg_lu_mpos[i]] = 1.0;
        return bg_lu_factor(m);
    }
    """

_cints(v) = isempty(v) ? "0" : join(string.(v), ", ")

function _ctable(io, name, size_expr, vals)
    println(io, "static const int $name[$size_expr] = {")
    for chunk in Iterators.partition(vals, 24)
        println(io, "    ", join(string.(chunk), ", "), ",")
    end
    isempty(vals) && println(io, "    0,")
    println(io, "};")
end

"""    emit_sparse_lu(io, lu; mass = ones(n))

The static index tables and the sparse side of the linear-algebra seam:
`bg_w_factor(m, hg)` forms W = M - hg·J on the static pattern from `m->jac` (which
`bg_jacobian` fills at the positions of the value array, see `jacobian_targets`) and the
mass diagonal `bg_mass` (at `lu_mass_positions`), and factors it in place in `m->lu`;
`bg_w_solve(m, b)` solves in place: pivot row k takes the right-hand side of equation
`bg_lu_rperm[k]` and gives the unknown `bg_lu_perm[k]`. With `project`, also
`bg_alg_factor(m)`, the sparse matrix of `bg_project`'s Newton step (`projection_matrix`)
on the same tables."""
function emit_sparse_lu(io, lu::StaticLU; mass::AbstractVector = ones(lu.n),
    project::Bool = false)
    nperm = lu_rows_permuted(lu)
    println(io, "/* Static sparse LU of W = M - hg J (D-EX13): pivot order $(join(lu.perm .- 1, " ")) (states), minimum degree. */")
    nperm > 0 && println(io, "/* Row matching: $nperm algebraic rows take their pivot off their own diagonal; pivot k is equation bg_lu_rperm[k], unknown bg_lu_perm[k]. */")
    println(io, "/* $(lu.nnz_w) non-zeros in W, $(lu_fill(lu)) fill-in, $(lu_nnz(lu)) in the factors; $(lu_flops(lu)) flops per factorization, $(lu_solve_flops(lu)) per solve. */")
    _ctable(io, "bg_lu_perm", "BG_NX", lu.perm .- 1)
    _ctable(io, "bg_lu_rperm", "BG_NX", lu.rperm .- 1)
    _ctable(io, "bg_lu_rowptr", "BG_NX + 1", lu.rowptr .- 1)
    _ctable(io, "bg_lu_col", "BG_LU_NNZ", lu.col .- 1)
    _ctable(io, "bg_lu_diag", "BG_NX", lu.diag .- 1)
    _ctable(io, "bg_lu_upd", "BG_SZ(BG_LU_NUPD)", lu.upd .- 1)
    # the position of the diagonal entry (i, i) of W, where the mass of state i is added
    _ctable(io, "bg_lu_mpos", "BG_NX", lu_mass_positions(lu, mass) .- 1)
    print(io, """

    /* No pivoting: the pivots are the diagonal of Pr W Pc' in the fixed order above (static
       pivoting; the stability argument is in src/export/sparse.jl). Each pivot must exceed
       BG_LU_TINY times the largest entry of its row, or the factorization fails. Every loop
       runs over the static tables, so the cost is fixed. */
    #define BG_LU_TINY $(repr(LU_TINY))

    static int bg_lu_factor(bg_model *m) {
        double *a = m->lu;
        int u = 0;
        for (int i = 0; i < BG_NX; ++i) {
            double s = 0.0;
            for (int p = bg_lu_rowptr[i]; p < bg_lu_rowptr[i + 1]; ++p) {
                const double v = fabs(a[p]);
                if (v > s) s = v;
            }
            for (int p = bg_lu_rowptr[i]; p < bg_lu_diag[i]; ++p) {
                const int k = bg_lu_col[p];
                const double l = a[p] * m->lu_inv[k];
                a[p] = l;
                for (int q = bg_lu_diag[k] + 1; q < bg_lu_rowptr[k + 1]; ++q)
                    a[bg_lu_upd[u++]] -= l * a[q];
            }
            const double d = a[bg_lu_diag[i]];
            if (!(fabs(d) > BG_LU_TINY * s)) return -1;
            m->lu_inv[i] = 1.0 / d;
        }
        return 0;
    }

    int bg_w_factor(bg_model *m, double hg) {
        double *a = m->lu;
        for (int p = 0; p < BG_LU_NNZ; ++p) a[p] = -hg * m->jac[p];
        for (int i = 0; i < BG_NX; ++i) a[bg_lu_mpos[i]] += bg_mass[i];
        return bg_lu_factor(m);
    }
    $(project ? _ALG_FACTOR_C : "")
    void bg_w_solve(bg_model *m, double *b) {
        const double *a = m->lu;
        double *y = m->lu_y;
        for (int k = 0; k < BG_NX; ++k) {
            double s = b[bg_lu_rperm[k]];
            for (int p = bg_lu_rowptr[k]; p < bg_lu_diag[k]; ++p) s -= a[p] * y[bg_lu_col[p]];
            y[k] = s;
        }
        for (int k = BG_NX - 1; k >= 0; --k) {
            double s = y[k];
            for (int p = bg_lu_diag[k] + 1; p < bg_lu_rowptr[k + 1]; ++p) s -= a[p] * y[bg_lu_col[p]];
            y[k] = s * m->lu_inv[k];
        }
        for (int k = 0; k < BG_NX; ++k) b[bg_lu_perm[k]] = y[k];
    }

    """)
end

"""    jacobian_targets(S, lu) -> Matrix{Int}

The 0-based index `bg_jacobian` writes the entry `(i, j)` to: row-major `i·nx + j` for the
dense LU (`lu === nothing`), the position in the static LU's value array otherwise (`(i, j)`
is row `i` of the C code, the equation in that row, whatever pivot the row matching gave
it). Entries outside `S` are -1."""
function jacobian_targets(S::AbstractMatrix{Bool}, lu::Union{Nothing,StaticLU})
    nx = size(S, 1)
    T = fill(-1, nx, nx)
    ip = lu === nothing ? Int[] : invperm(lu.perm)
    ipr = lu === nothing ? Int[] : invperm(lu.rperm)
    for j in 1:nx, i in 1:nx
        S[i, j] || continue
        if lu === nothing
            T[i, j] = (i - 1) * nx + (j - 1)
        else
            p = lu_position(lu, i, j, ip, ipr)
            p > 0 || throw(ExportError("internal: the Jacobian entry ($i, $j) is outside the LU pattern"))
            T[i, j] = p - 1
        end
    end
    return T
end

"""    emit_fd_jacobian(io, S, colour, targets)

`bg_jacobian` by forward differences with column colouring (D-EX12 fallback): one call of
`bg_derivatives` at x, then one per colour with every column of that colour perturbed at
once. The step of column j is sqrt(eps)·max(1, |x_j|), rounded to a representable
difference. The workspace lives on the stack (4·BG_NX doubles); nothing is allocated."""
function emit_fd_jacobian(io, S::AbstractMatrix{Bool}, colour::Vector{Int}, targets::Matrix{Int})
    nx = size(S, 1)
    nc = isempty(colour) ? 0 : maximum(colour)
    cols = Int[]
    cptr = [0]
    rows = Int[]
    jcol = Int[]
    dst = Int[]
    nptr = [0]
    for c in 1:nc
        for j in 1:nx
            colour[j] == c || continue
            push!(cols, j - 1)
            for i in 1:nx
                S[i, j] || continue
                push!(rows, i - 1)
                push!(jcol, j - 1)
                push!(dst, targets[i, j])
            end
        end
        push!(cptr, length(cols))
        push!(nptr, length(rows))
    end
    println(io, "/* Coloured finite-difference Jacobian (D-EX12 fallback): $(length(rows)) structural non-zeros in $nc colours, so $(nc + 1) derivative calls. */")
    println(io, "#define BG_FD_NCOLOUR $nc")
    println(io, "#define BG_FD_NNZ $(length(rows))")
    _ctable(io, "bg_fd_cptr", "BG_FD_NCOLOUR + 1", cptr)
    _ctable(io, "bg_fd_cols", "BG_NX", cols)
    _ctable(io, "bg_fd_nptr", "BG_FD_NCOLOUR + 1", nptr)
    _ctable(io, "bg_fd_row", "BG_SZ(BG_FD_NNZ)", rows)
    _ctable(io, "bg_fd_col", "BG_SZ(BG_FD_NNZ)", jcol)
    _ctable(io, "bg_fd_dst", "BG_SZ(BG_FD_NNZ)", dst)
    print(io, """
    void bg_jacobian(const bg_model *m, double t, const double *x, double *J) {
        double xp[BG_NX], f0[BG_NX], f1[BG_NX], h[BG_NX];
        bg_derivatives(m, t, x, f0);
        for (int i = 0; i < BG_NX; ++i) xp[i] = x[i];
        for (int c = 0; c < BG_FD_NCOLOUR; ++c) {
            for (int q = bg_fd_cptr[c]; q < bg_fd_cptr[c + 1]; ++q) {
                const int j = bg_fd_cols[q];
                xp[j] = x[j] + 1.4901161193847656e-08 * bg_max(fabs(x[j]), 1.0);
                h[j] = xp[j] - x[j];
            }
            bg_derivatives(m, t, xp, f1);
            for (int e = bg_fd_nptr[c]; e < bg_fd_nptr[c + 1]; ++e)
                J[bg_fd_dst[e]] = (f1[bg_fd_row[e]] - f0[bg_fd_row[e]]) / h[bg_fd_col[e]];
            for (int q = bg_fd_cptr[c]; q < bg_fd_cptr[c + 1]; ++q) xp[bg_fd_cols[q]] = x[bg_fd_cols[q]];
        }
    }

    """)
end

"""    emit_jacobian(io, la, jc)

`bg_jacobian` for the plan `la` (`nothing` when no method needs a Jacobian: an empty
function): the symbolic entries of `jc` (`jacobian_c`) at `la.targets`, or the coloured
finite differences. The caller zeroes J first."""
function emit_jacobian(io, la, jc)
    sig = "void bg_jacobian(const bg_model *m, double t, const double *x, double *J)"
    if la === nothing
        println(io, "/* Empty: an explicit method needs no Jacobian. */")
        println(io, sig, " {\n    (void)m; (void)t; (void)x; (void)J;\n}\n")
        return
    end
    layout = la.lu === nothing ? "row-major (dense LU)" : "at its position in the static LU's value array"
    if la.jacobian === :fd
        println(io, "/* J[i][j] is written $layout. */")
        emit_fd_jacobian(io, la.pattern, la.colour, la.targets)
        return
    end
    println(io, "/* Symbolic Jacobian, every partial of every observed local computed once; J[i][j] is written $layout. The caller zeroes J, so only the structural non-zeros are written. */")
    println(io, sig, " {")
    println(io, "    (void)m; (void)t; (void)x; (void)J;")
    print(io, render_jacobian(jc, la.targets))
    println(io, "}\n")
end

# ---------------------------------------------------------------------------------------
# Choosing the Jacobian and the linear solver

_dense_lu_flops(n) = sum((n - k) + 2 * (n - k)^2 for k in 1:n; init = 0) + n

"""    _use_sparse(settings, nx) -> Bool

The linear solver before the pivot check (D-EX13): the static sparse LU above
`settings.sparse_threshold` states, or when forced."""
_use_sparse(settings, nx) = settings.linear_solver === :auto ?
    nx > settings.sparse_threshold : settings.linear_solver === :sparse

"""True when every pivot of W = M - hγ·J is structurally non-zero without a row matching:
each diagonal entry is in the pattern `S` or carries a mass."""
_diagonal_structural(S::AbstractMatrix{Bool}, mass::AbstractVector) =
    all(i -> S[i, i] || !iszero(mass[i]), 1:size(S, 1))

"""    structural_lu(S, mass) -> StaticLU

The static LU the cost model and the simplification report price before any Jacobian is
evaluated: without a row matching when the diagonal of W is structurally full, with the
structural matching (`row_matching` without Jacobians) otherwise."""
structural_lu(S::AbstractMatrix{Bool}, mass::AbstractVector) =
    _diagonal_structural(S, mass) ? static_lu(S) :
    static_lu(S; rowmatch = row_matching(S, mass).rowmatch)

"""    _plan_linear_algebra(jplan, settings, nx, hg, mass, Js, diags) -> NamedTuple

The linear solver (D-EX13) for the pattern and Jacobian kind of `jplan`: the static sparse
LU when `_use_sparse`, else the dense LU. The sparse LU must pass `static_lu_check` for
W = M - hg·J at the Jacobians `Js` (the scanned points, in the rows of the C code), with
`hg` = γh of the chosen method. Its pivots are W's own diagonal when that is structurally
full and passes the check; otherwise the row matching (`row_matching`, weighted by `Js`) is
tried, and kept when it passes (or when the diagonal has a structural zero, where the
identity cannot). When the check still fails, `:auto` falls back to dense and a forced
`:sparse` keeps it, both with W211. Returns the pattern, colouring, targets, the `StaticLU`
(or `nothing`) and the report entry."""
function _plan_linear_algebra(jplan, settings, nx, hg, mass, Js, diags)
    S = jplan.pattern
    colour = colour_columns(S)
    colouring_valid(S, colour) ||
        throw(ExportError("internal: the column colouring of the Jacobian pattern is invalid"))
    ncol = maximum(colour; init = 0)
    full_diag = _diagonal_structural(S, mass)
    t0 = time()
    slu = static_lu(S)
    symbolic_s = time() - t0
    check = full_diag ? static_lu_check(slu, Js, hg; mass) : nothing
    # The row matching: tried when the identity cannot be used (a structural zero on the
    # diagonal) or fails the check; kept when it passes, or does better than the identity.
    tried = false
    match = (rowmatch = collect(1:nx), complete = true, weighted = false, permuted = 0)
    if !full_diag || !check.ok
        tried = true
        t0 = time()
        m = row_matching(S, mass; Js)
        mlu = m.permuted > 0 ? static_lu(S; rowmatch = m.rowmatch) : nothing
        symbolic_s += time() - t0
        if mlu !== nothing
            mcheck = static_lu_check(mlu, Js, hg; mass)
            if check === nothing || mcheck.ok || mcheck.min_pivot_ratio > check.min_pivot_ratio
                slu, check, match = mlu, mcheck, m
            end
        end
        check === nothing && (check = static_lu_check(slu, Js, hg; mass))
    end
    solver = _use_sparse(settings, nx) ? :sparse : :dense
    if solver === :sparse && !check.ok
        forced = settings.linear_solver === :sparse
        matched = !tried ? "without a row matching" :
            match.permuted > 0 ? "with a row matching" :
            "without a row matching (the row matching was tried and did not help)"
        push!(diags, diag("W211",
            "the static sparse LU (no pivoting) failed its check at the scanned points $matched: smallest pivot ratio $(round(check.min_pivot_ratio; sigdigits = 3)), backward error $(round(check.backward_error; sigdigits = 3))" *
            (forced ? "; it is kept because the sparse solver was forced" :
                ", so the dense LU with partial pivoting is used");
            hint = forced ? "use linear_solver = auto or dense, or a smaller dt" :
                "a smaller dt makes W = M - hγJ more diagonally dominant (an algebraic row has no M to help)"))
        forced || (solver = :dense)
    end
    lu = solver === :sparse ? slu : nothing
    targets = jacobian_targets(S, lu)
    # bg_project's Newton step (a DAE re-solves its algebraic unknowns after a tick or an
    # event) on the same static tables, when its pivots pass the check too; otherwise a dense
    # Gaussian elimination of the algebraic block, as with the dense LU.
    nalg = count(iszero, mass)
    pcheck = lu !== nothing && nalg > 0 ? projection_check(lu, Js, mass) : nothing
    project = pcheck !== nothing && pcheck.ok
    report = Dict{String,Any}(
        "jacobian" => String(jplan.kind), "linearSolver" => String(solver),
        "nnzJ" => count(S), "colours" => ncol,
        "fdDerivativeCalls" => jplan.kind === :fd ? ncol + 1 : nothing,
        "ordering" => "minimum degree", "nnzW" => slu.nnz_w, "nnzLU" => lu_nnz(slu),
        "fillIn" => lu_fill(slu),
        "luFlops" => solver === :sparse ? lu_flops(slu) : _dense_lu_flops(nx),
        "solveFlops" => solver === :sparse ? lu_solve_flops(slu) : 2 * nx * nx - nx,
        "sparseLuFlops" => lu_flops(slu), "denseLuFlops" => _dense_lu_flops(nx),
        "symbolicFactorS" => symbolic_s, "hGamma" => hg,
        # The row matching (D-EX13): `tried` when the identity was not enough, `used` when
        # the sparse LU above has its rows matched (`rowsPermuted` off their diagonal).
        # The LU counts above are those of the static LU the check ended with.
        "matching" => Dict("tried" => tried, "used" => match.permuted > 0,
            "rowsPermuted" => match.permuted, "weighted" => match.weighted,
            "structuralDiagonal" => full_diag),
        "pivotCheck" => Dict("ok" => check.ok, "points" => check.points,
            "minPivotRatio" => check.min_pivot_ratio, "growth" => check.growth,
            "residual" => check.residual, "backwardError" => check.backward_error),
        # The re-solve of the algebraic unknowns (bg_project): `sparse` on the static tables,
        # else the dense elimination of the BG_NALG x BG_NALG block (nothing: no DAE).
        "projection" => nalg == 0 ? nothing : Dict("sparse" => project,
            "denseFlops" => _dense_lu_flops(nalg),
            "pivotCheck" => pcheck === nothing ? nothing : Dict("ok" => pcheck.ok,
                "points" => pcheck.points, "minPivotRatio" => pcheck.min_pivot_ratio,
                "growth" => pcheck.growth, "residual" => pcheck.residual,
                "backwardError" => pcheck.backward_error)),
    )
    merge!(report, jplan.stats)
    return (pattern = S, jacobian = jplan.kind, colour = colour, targets = targets, lu = lu,
        project = project, report = report)
end
