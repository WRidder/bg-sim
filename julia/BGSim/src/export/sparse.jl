# Sparse Jacobian, static sparse LU and the coloured finite-difference Jacobian
# (plan/EXPORT_PLAN.md D-EX12, D-EX13, work package J-EX4).
#
# A Rosenbrock step solves with W = M - hγ·J. Everything about the sparsity of W is decided
# here, at export, so the C code does a fixed amount of work in a fixed order:
#
#   pattern     `jacobian_pattern`: S[i, j] when d/dt x_i can depend on x_j. It follows the
#               variables of the right-hand side through the observed equations, so it is the
#               structure, not the numeric zeros of one point (those can be accidental).
#   ordering    `minimum_degree_order`: a fill-reducing symmetric permutation of the pattern
#               of W (exact minimum degree on S + Sᵀ, ties to the lowest index).
#   factors     `static_lu`: the symbolic LU of P·W·Pᵀ with no pivoting. The fill-in, the
#               row-compressed layout and every multiply-add are fixed; C runs them from
#               static index tables (`emit_sparse_lu`).
#   colouring   `colour_columns`: a greedy distance-2 colouring of the columns of S. Columns
#               of one colour share no row, so one derivative call per colour gives all their
#               Jacobian entries (`emit_fd_jacobian`, the D-EX12 fallback).
#
# Static pivoting. The pivots are the diagonal of P·W·Pᵀ in a fixed order, so a step never
# searches for a pivot or moves a row. For an ODE this is safe when W is diagonally
# dominant, which holds for small hγ (W → M = I), and when the symmetric part of W is
# positive definite, which holds when J is dissipative (J + Jᵀ ≤ 0): every pivot is then at
# least 1. An algebraic row of a DAE has mass 0, so its pivot comes from J alone and small
# hγ does not help. Neither is guaranteed in general, so (a) `bg_w_factor` checks every
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

The symbolic LU of `P·W·Pᵀ` without pivoting (1-based; the C tables are the same minus 1).

| field | meaning |
| --- | --- |
| `perm` | `perm[k]` is the state of pivot `k` |
| `rowptr`, `col` | the filled pattern, row-compressed with sorted columns: row `k` holds L (columns `< k`), the pivot, then U |
| `diag` | position of the pivot of row `k` |
| `upd` | the destination of every multiply-add `a[upd[u]] -= l·a[q]`, in factorization order |
| `nnz_w` | non-zeros of the pattern of W before fill (J plus the diagonal) |
"""
struct StaticLU
    n::Int
    perm::Vector{Int}
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

"""    static_lu(S; order = minimum_degree_order(S)) -> StaticLU

The symbolic factorization of the pattern `S ∪ I` permuted by `order`."""
function static_lu(S::AbstractMatrix{Bool}; order::Vector{Int} = minimum_degree_order(S))
    n = size(S, 1)
    sort(order) == collect(1:n) || throw(ArgumentError("`order` is not a permutation of 1:$n"))
    B = falses(n, n)
    for j in 1:n, i in 1:n
        B[i, j] = S[order[i], order[j]] || i == j
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
    return StaticLU(n, copy(order), rowptr, col, diag, upd, count(B))
end

"""    lu_position(lu, i, j, ip = invperm(lu.perm)) -> Int

The position of the entry `(i, j)` of W (state indices) in the value array, or 0 when it is
outside the pattern."""
function lu_position(lu::StaticLU, i::Int, j::Int, ip::Vector{Int} = invperm(lu.perm))
    r, c = ip[i], ip[j]
    for p in lu.rowptr[r]:lu.rowptr[r + 1] - 1
        lu.col[p] == c && return p
    end
    return 0
end

"""    lu_values(lu, W) -> Vector{Float64}

The entries of the dense matrix `W` on the value layout of `lu` (fill positions zero)."""
function lu_values(lu::StaticLU, W::AbstractMatrix)
    a = zeros(lu_nnz(lu))
    for r in 1:lu.n, p in lu.rowptr[r]:lu.rowptr[r + 1] - 1
        a[p] = W[lu.perm[r], lu.perm[lu.col[p]]]
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
        s = b[lu.perm[k]]
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

"""    static_lu_check(lu, Js, hg; mass = ones(n)) -> NamedTuple

Factor `W = M - hg·J` (`M = diag(mass)`; an algebraic row has mass 0, so its pivot comes
from J alone) for every Jacobian in `Js` with the static pivots and report the smallest
pivot ratio |u_kk| / (largest entry of its row of W), the growth (largest entry of the
factors over the largest entry of W) and the relative residual of a solve against a pivoted
dense solve. `ok` is false when a factorization failed or the residual is above 1e-8."""
function static_lu_check(lu::StaticLU, Js, hg::Float64; mass::AbstractVector = ones(lu.n))
    n = lu.n
    min_ratio, growth, residual, points = Inf, 0.0, 0.0, 0
    ok = true
    for J in Js
        all(isfinite, J) || continue
        W = Matrix{Float64}(LinearAlgebra.Diagonal(Float64.(mass))) .- hg .* J
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
        xd = W \ b
        residual = max(residual, maximum(abs, x .- xd) / max(maximum(abs, xd), floatmin()))
    end
    residual > 1e-8 && (ok = false)
    return (ok = ok, points = points, min_pivot_ratio = isfinite(min_ratio) ? min_ratio : 1.0,
        growth = growth, residual = residual)
end

# ---------------------------------------------------------------------------------------
# C emission

_cints(v) = isempty(v) ? "0" : join(string.(v), ", ")

function _ctable(io, name, size_expr, vals)
    println(io, "static const int $name[$size_expr] = {")
    for chunk in Iterators.partition(vals, 24)
        println(io, "    ", join(string.(chunk), ", "), ",")
    end
    isempty(vals) && println(io, "    0,")
    println(io, "};")
end

"""    emit_sparse_lu(io, lu)

The static index tables and the sparse side of the linear-algebra seam:
`bg_w_factor(m, hg)` forms W = M - hg·J on the static pattern from `m->jac` (which
`bg_jacobian` fills at the positions of the value array, see `jacobian_targets`) and the
mass diagonal `bg_mass`, and factors it in place in `m->lu`; `bg_w_solve(m, b)` solves in
place."""
function emit_sparse_lu(io, lu::StaticLU)
    n = lu.n
    ip = invperm(lu.perm)
    println(io, "/* Static sparse LU of W = M - hg J (D-EX13): pivot order $(join(lu.perm .- 1, " ")) (states), minimum degree. */")
    println(io, "/* $(lu.nnz_w) non-zeros in W, $(lu_fill(lu)) fill-in, $(lu_nnz(lu)) in the factors; $(lu_flops(lu)) flops per factorization, $(lu_solve_flops(lu)) per solve. */")
    _ctable(io, "bg_lu_perm", "BG_NX", lu.perm .- 1)
    _ctable(io, "bg_lu_rowptr", "BG_NX + 1", lu.rowptr .- 1)
    _ctable(io, "bg_lu_col", "BG_LU_NNZ", lu.col .- 1)
    _ctable(io, "bg_lu_diag", "BG_NX", lu.diag .- 1)
    _ctable(io, "bg_lu_upd", "BG_SZ(BG_LU_NUPD)", lu.upd .- 1)
    # the position of the diagonal entry of state i, where M is added
    _ctable(io, "bg_lu_mpos", "BG_NX", [lu.diag[ip[i]] - 1 for i in 1:n])
    print(io, """

    /* No pivoting: the pivots are the diagonal of P W P' in the fixed order above (static
       pivoting; the stability argument is in src/export/sparse.jl). Each pivot must exceed
       BG_LU_TINY times the largest entry of its row, or the factorization fails. Every loop
       runs over the static tables, so the cost is fixed. */
    #define BG_LU_TINY $(repr(LU_TINY))

    int bg_w_factor(bg_model *m, double hg) {
        double *a = m->lu;
        int u = 0;
        for (int p = 0; p < BG_LU_NNZ; ++p) a[p] = -hg * m->jac[p];
        for (int i = 0; i < BG_NX; ++i) a[bg_lu_mpos[i]] += bg_mass[i];
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

    void bg_w_solve(bg_model *m, double *b) {
        const double *a = m->lu;
        double *y = m->lu_y;
        for (int k = 0; k < BG_NX; ++k) {
            double s = b[bg_lu_perm[k]];
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
dense LU (`lu === nothing`), the position in the static LU's value array otherwise. Entries
outside `S` are -1."""
function jacobian_targets(S::AbstractMatrix{Bool}, lu::Union{Nothing,StaticLU})
    nx = size(S, 1)
    T = fill(-1, nx, nx)
    ip = lu === nothing ? Int[] : invperm(lu.perm)
    for j in 1:nx, i in 1:nx
        S[i, j] || continue
        if lu === nothing
            T[i, j] = (i - 1) * nx + (j - 1)
        else
            p = lu_position(lu, i, j, ip)
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

"""    _check_jacobians(jac_fn, x0, p0, names_x, names_p, reference_dir; samples = 5)

Numeric Jacobians at the initial point and at a few rows of the reference run, for the
static pivot check."""
function _check_jacobians(jac_fn, x0, p0, names_x, names_p, reference_dir; samples::Int = 5)
    Js = Matrix{Float64}[jac_fn(x0, p0, 0.0)]
    (reference_dir === nothing || !isfile(joinpath(reference_dir, "stream.f64"))) && return Js
    ids, rows = _reference_rows(reference_dir)
    col = Dict(id => i + 1 for (i, id) in enumerate(ids))
    for r in unique(round.(Int, range(1, length(rows); length = min(samples, length(rows)))))
        row = rows[r]
        x = Float64[haskey(col, n) ? row[col[n]] : x0[i] for (i, n) in enumerate(names_x)]
        p = Float64[haskey(col, n) ? row[col[n]] : p0[i] for (i, n) in enumerate(names_p)]
        all(isfinite, x) || continue
        push!(Js, jac_fn(x, p, row[1]))
    end
    return Js
end

_dense_lu_flops(n) = sum((n - k) + 2 * (n - k)^2 for k in 1:n; init = 0) + n

"""    _use_sparse(settings, nx) -> Bool

The linear solver before the pivot check (D-EX13): the static sparse LU above
`settings.sparse_threshold` states, or when forced."""
_use_sparse(settings, nx) = settings.linear_solver === :auto ?
    nx > settings.sparse_threshold : settings.linear_solver === :sparse

"""    _plan_linear_algebra(jplan, settings, nx, hg, mass, Js, diags) -> NamedTuple

The linear solver (D-EX13) for the pattern and Jacobian kind of `jplan`: the static sparse
LU when `_use_sparse`, else the dense LU. The sparse LU must pass `static_lu_check` for
W = M - hg·J at the Jacobians `Js` (in the rows of the C code), with `hg` = γh of the chosen
method; when it does not, `:auto` falls back to dense and a forced `:sparse` keeps it, both
with W211. Returns the pattern, colouring, targets, the `StaticLU` (or `nothing`) and the
report entry."""
function _plan_linear_algebra(jplan, settings, nx, hg, mass, Js, diags)
    S = jplan.pattern
    colour = colour_columns(S)
    colouring_valid(S, colour) ||
        throw(ExportError("internal: the column colouring of the Jacobian pattern is invalid"))
    ncol = maximum(colour; init = 0)
    t0 = time()
    slu = static_lu(S)
    symbolic_s = time() - t0
    check = static_lu_check(slu, Js, hg; mass)
    solver = _use_sparse(settings, nx) ? :sparse : :dense
    if solver === :sparse && !check.ok
        forced = settings.linear_solver === :sparse
        push!(diags, diag("W211",
            "the static sparse LU (no pivoting) failed its check at the scanned points: smallest pivot ratio $(round(check.min_pivot_ratio; sigdigits = 3)), residual $(round(check.residual; sigdigits = 3))" *
            (forced ? "; it is kept because the sparse solver was forced" :
                ", so the dense LU with partial pivoting is used");
            hint = forced ? "use linear_solver = auto or dense, or a smaller dt" :
                "a smaller dt makes W = M - hγJ more diagonally dominant (an algebraic row has no M to help)"))
        forced || (solver = :dense)
    end
    lu = solver === :sparse ? slu : nothing
    targets = jacobian_targets(S, lu)
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
        "pivotCheck" => Dict("ok" => check.ok, "points" => check.points,
            "minPivotRatio" => check.min_pivot_ratio, "growth" => check.growth,
            "residual" => check.residual),
    )
    merge!(report, jplan.stats)
    return (pattern = S, jacobian = jplan.kind, colour = colour, targets = targets, lu = lu,
        report = report)
end
