# Work package J-EX4: sparse Jacobian pattern, static sparse LU, coloured finite differences
# (plan/EXPORT_PLAN.md D-EX12, D-EX13).
#
#   * the static LU (symbolic factorization with minimum degree, no pivoting) solves like a
#     pivoted dense LU on random patterns, in Julia and in the generated C;
#   * minimum degree removes the fill of an arrowhead matrix; a zero pivot is refused;
#   * the column colouring is valid on random patterns and recovers a sparse Jacobian from
#     one compressed difference per colour;
#   * a ring of coupled nonlinear lags exports with ROS2 in every combination of
#     {dense, sparse} x {symbolic, fd}; the FMUs agree with each other (when gcc is on PATH).

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile
import Random
import LinearAlgebra

const _SP = BGSim.Export

function _sp_random_pattern(rng, n, density)
    S = falses(n, n)
    for j in 1:n, i in 1:n
        S[i, j] = i == j || rand(rng) < density
    end
    return S
end

# W = I - hg J with J on the pattern S and a diagonal that keeps W comfortably nonsingular
# without pivoting.
function _sp_random_w(rng, S, hg)
    n = size(S, 1)
    J = zeros(n, n)
    for j in 1:n, i in 1:n
        S[i, j] && (J[i, j] = randn(rng))
    end
    for i in 1:n
        J[i, i] = -abs(J[i, i]) - sum(abs, view(J, i, :))
    end
    return J, Matrix{Float64}(LinearAlgebra.I, n, n) .- hg .* J
end

# A DAE-shaped Jacobian with `nd` differential and `na` algebraic rows (mass 1 and 0, the
# differential rows first): the algebraic block ∂g/∂z has a dominant permutation (a cyclic
# shift) and no diagonal, so W = M - hγJ has a structural zero on every algebraic pivot,
# as the rigid-joint Panda's ordering gives.
function _sp_random_dae(rng, nd, na)
    n = nd + na
    S = falses(n, n)
    J = zeros(n, n)
    for i in 1:nd, j in 1:n
        (i == j || rand(rng) < 0.15) && (S[i, j] = true; J[i, j] = randn(rng))
    end
    for a in 1:na
        i = nd + a
        j = nd + mod1(a + 1, na)
        S[i, j] = true
        J[i, j] = (rand(rng) < 0.5 ? -1 : 1) * (4.0 + abs(randn(rng)))
        for k in 1:n
            k == i && continue
            !S[i, k] && rand(rng) < 0.06 && (S[i, k] = true; J[i, k] = 0.5 * randn(rng))
        end
    end
    return S, [i <= nd ? 1.0 : 0.0 for i in 1:n], J
end

function _sp_chain_block(n)
    vars = join(["        x$i::Real = $(0.1 * i)" for i in 1:n], "\n")
    eqs = String[]
    for i in 1:n
        left = i == 1 ? "u + x$n" : "x$(i - 1)"
        right = i == n ? "x1" : "x$(i + 1)"
        push!(eqs, "        ddt(x$i) ~ k * ($left - 3 * x$i + $right) - c * x$i^3")
    end
    push!(eqs, "        y ~ x$n")
    return """
    @block Ring begin
        @inputs u::Real
        @outputs y::Real
        @parameters k::Real = 200.0
        @parameters c::Real = 5.0
        @variables begin
    $vars
        end
        @equations begin
    $(join(eqs, "\n"))
        end
    end
    """
end

# n unit masses joined by stiff spring-dampers (k = 1e8), pushed by u: W = I - hγJ is far
# from diagonally dominant, so the dense LU exchanges rows.
function _sp_masses_block(n)
    vars = join(vcat(["        q$i::Real = 0.0" for i in 1:n], ["        v$i::Real = 0.0" for i in 1:n]), "\n")
    eqs = String[]
    for i in 1:n
        push!(eqs, "        ddt(q$i) ~ v$i")
        f = i == 1 ? "u" : "k * (q$(i - 1) - q$i) + c * (v$(i - 1) - v$i)"
        i < n && (f *= " - k * (q$i - q$(i + 1)) - c * (v$i - v$(i + 1))")
        push!(eqs, "        ddt(v$i) ~ $f")
    end
    push!(eqs, "        y ~ q$n")
    return """
    @block Masses begin
        @inputs u::Real
        @outputs y::Real
        @parameters k::Real = 1.0e8
        @parameters c::Real = 1.0e3
        @variables begin
    $vars
        end
        @equations begin
    $(join(eqs, "\n"))
        end
    end
    """
end

function _sp_ring_model(n; block = _sp_chain_block(n))
    src = Dict{String,Any}("inline" => Dict{String,Any}("source" => block))
    nodes = Any[
        bg_node("n1", "U", bg_ref("stdlib:converters/ExportInput");
            params = Dict{String,Any}("value" => "1.0")),
        bg_node("n2", "Plant", src),
        bg_node("n3", "Y", bg_ref("stdlib:converters/ExportOutput")),
    ]
    conns = Any[bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "signal", "n2", "y", "n3", "u")]
    return Compile.flatten(IR.parse_model(bg_model("ExportRing", nodes, conns; t_end = 0.1, points = 11)))
end

@testset "export sparse linear algebra (J-EX4)" begin
    @testset "static LU solves like a pivoted dense LU on random patterns" begin
        rng = Random.MersenneTwister(4)
        for n in (1, 2, 7, 30, 80), density in (0.05, 0.2)
            S = _sp_random_pattern(rng, n, density)
            lu = _SP.static_lu(S)
            @test sort(lu.perm) == collect(1:n)
            @test all(lu.col[lu.diag[k]] == k for k in 1:n)
            @test lu.nnz_w == count(S .| Matrix{Bool}(LinearAlgebra.I, n, n))
            _, W = _sp_random_w(rng, S, 0.3)
            a = _SP.lu_values(lu, W)
            inv = zeros(n)
            @test _SP.lu_factor!(a, lu, inv)
            b = randn(rng, n)
            x = _SP.lu_solve!(copy(b), a, lu, inv)
            @test isapprox(x, W \ b; rtol = 1e-10)
            # the factors reproduce W on the permuted pattern
            L = Matrix{Float64}(LinearAlgebra.I, n, n)
            U = zeros(n, n)
            for k in 1:n, p in lu.rowptr[k]:lu.rowptr[k + 1] - 1
                c = lu.col[p]
                c < k ? (L[k, c] = a[p]) : (U[k, c] = a[p])
            end
            @test isapprox(L * U, W[lu.perm, lu.perm]; rtol = 1e-12, atol = 1e-12)
        end
    end

    @testset "minimum degree, fill-in and the pivot check" begin
        # An arrowhead with the hub first fills completely in the natural order and not at
        # all when the hub is eliminated last.
        n = 12
        S = falses(n, n)
        for i in 1:n
            S[i, i] = S[1, i] = S[i, 1] = true
        end
        natural = _SP.static_lu(S; order = collect(1:n))
        md = _SP.static_lu(S)
        @test _SP.lu_fill(natural) == (n - 1) * (n - 2)
        @test _SP.lu_fill(md) == 0
        @test 1 in md.perm[end - 1:end]          # the hub goes last (a tie with the last leaf)
        @test _SP.lu_flops(md) < _SP.lu_flops(natural)

        # a zero pivot is refused, a tiny one too
        S2 = trues(2, 2)
        lu2 = _SP.static_lu(S2; order = [1, 2])
        @test !_SP.lu_factor!(_SP.lu_values(lu2, [0.0 1.0; 1.0 0.0]), lu2, zeros(2))
        @test !_SP.lu_factor!(_SP.lu_values(lu2, [1.0 1.0; 1.0 1.0 + 1e-15]), lu2, zeros(2))
        chk = _SP.static_lu_check(lu2, [[0.0 1.0; 1.0 0.0]], 1.0)  # W = [1 -1; -1 1]: singular
        @test !chk.ok
        chk = _SP.static_lu_check(lu2, [[-1.0 0.5; 0.5 -1.0]], 1e-3)
        @test chk.ok && chk.min_pivot_ratio > 0.99 && chk.residual < 1e-14
        @test chk.backward_error < 1e-15
        # a small pivot passes the 1e-12 ratio test, but the growth (1e11) makes the solve
        # unstable: the backward error rejects it (W = [1e-11 1; 1 1], algebraic rows)
        chk = _SP.static_lu_check(lu2, [-[1e-11 1.0; 1.0 1.0]], 1.0; mass = [0.0, 0.0])
        @test chk.min_pivot_ratio > 1e-12 && chk.growth > 1e10
        @test !chk.ok && chk.backward_error > _SP.LU_BACKWARD_ERROR
        # a badly row-scaled W (an algebraic row scaled by hγ = 1e-9) is no reason to fail
        chk = _SP.static_lu_check(lu2, [[-1.0 0.5; 2.0 -3.0]], 1e-9; mass = [1.0, 0.0])
        @test chk.ok && chk.backward_error < 1e-15
    end

    @testset "row matching: a structural pivot on every row" begin
        rng = Random.MersenneTwister(21)
        for n in (2, 5, 30, 120)
            # no structural diagonal at all: a cyclic shift plus random off-diagonal entries
            P = falses(n, n)
            for j in 1:n
                P[mod1(j + 1, n), j] = true
            end
            for j in 1:n, i in 1:n
                i != j && rand(rng) < 0.05 && (P[i, j] = true)
            end
            m = _SP.structural_matching(P)
            @test sort(m) == collect(1:n)
            @test all(P[m[j], j] for j in 1:n)
            @test _SP.structural_matching(copy(P)) == m           # deterministic
            # a structural diagonal is kept
            D = P .| Matrix{Bool}(LinearAlgebra.I, n, n)
            @test _SP.structural_matching(D) == collect(1:n)
        end
        # structurally singular: an empty column stays unmatched
        Z = trues(3, 3)
        Z[:, 2] .= false
        @test count(==(0), _SP.structural_matching(Z)) == 1

        # rows with mass keep their diagonal; the algebraic rows (3, 4, 5) are matched on
        # their block, whose diagonal is empty
        S = falses(5, 5)
        S[1, 3] = S[2, 4] = true                      # differential rows read z
        S[3, 1] = S[3, 4] = S[4, 5] = S[5, 3] = S[5, 4] = true
        mass = [1.0, 1.0, 0.0, 0.0, 0.0]
        m = _SP.row_matching(S, mass)
        @test m.rowmatch[1:2] == [1, 2] && m.complete && !m.weighted
        @test all(j -> S[m.rowmatch[j], j] || mass[j] != 0, 1:5)
        @test m.permuted == 3
        @test _SP.row_matching(S, mass) == m
        # weighted: both pairings of a full 2x2 algebraic block are structural; the larger
        # entries win, and a tie keeps the diagonal
        S2 = falses(3, 3)
        S2[2:3, 2:3] .= true
        J = [0.0 0.0 0.0; 0.0 1.0e-6 1.0; 0.0 1.0 1.0e-6]
        mw = _SP.row_matching(S2, [1.0, 0.0, 0.0]; Js = [J])
        @test mw.weighted && mw.rowmatch == [1, 3, 2]
        J[2:3, 2:3] .= 1.0
        @test _SP.row_matching(S2, [1.0, 0.0, 0.0]; Js = [J]).rowmatch == [1, 2, 3]
        @test _SP.row_matching(S2, [1.0, 0.0, 0.0]).rowmatch == [1, 2, 3]
        # an entry that is zero at a scanned point loses to one that never is
        J1 = [0.0 0.0 0.0; 0.0 1.0 0.5; 0.0 0.5 1.0]
        J2 = [0.0 0.0 0.0; 0.0 0.0 0.5; 0.0 0.5 1.0]
        @test _SP.row_matching(S2, [1.0, 0.0, 0.0]; Js = [J1, J2]).rowmatch == [1, 3, 2]
    end

    @testset "the row-matched static LU solves a DAE with a zero diagonal" begin
        rng = Random.MersenneTwister(23)
        for (nd, na) in ((3, 4), (10, 30), (14, 140))
            S, mass, J = _sp_random_dae(rng, nd, na)
            n = nd + na
            hg = 1.0e-3
            W = LinearAlgebra.Diagonal(mass) .- hg .* J
            @test !_SP._diagonal_structural(S, mass)
            m = _SP.row_matching(S, mass; Js = [J])
            @test m.complete && m.permuted > 0
            lu = _SP.static_lu(S; rowmatch = m.rowmatch)
            @test _SP.lu_rows_permuted(lu) == m.permuted
            @test all(lu.col[lu.diag[k]] == k for k in 1:n)
            chk = _SP.static_lu_check(lu, [J], hg; mass)
            @test chk.ok
            a = _SP.lu_values(lu, W)
            inv = zeros(n)
            @test _SP.lu_factor!(a, lu, inv)
            b = randn(rng, n)
            @test isapprox(_SP.lu_solve!(copy(b), a, lu, inv), W \ b; rtol = 1e-9)
            # the plan: J written at its targets plus M at the mass positions is W on the
            # layout of the LU (what bg_jacobian and bg_w_factor do in C), and dg/dz is found
            # through the targets (bg_alg_jpos)
            diags = BGSim.Diagnostic[]
            la = _SP._plan_linear_algebra((pattern = S, kind = :symbolic, stats = Dict{String,Any}()),
                _SP.ExportSettings(linear_solver = :auto, sparse_threshold = 1), n, hg, mass, [J], diags)
            @test la.lu !== nothing && isempty(diags)
            rep = la.report
            @test rep["matching"]["used"] && rep["matching"]["tried"] && rep["matching"]["weighted"]
            @test rep["matching"]["rowsPermuted"] == m.permuted && !rep["matching"]["structuralDiagonal"]
            @test rep["luFlops"] == _SP.lu_flops(la.lu) && rep["nnzLU"] == _SP.lu_nnz(la.lu)
            # bg_project's Newton matrix factors on the same tables
            @test la.project && rep["projection"]["sparse"] && rep["projection"]["pivotCheck"]["ok"]
            v = zeros(_SP.lu_nnz(la.lu))
            for j in 1:n, i in 1:n
                S[i, j] && (v[la.targets[i, j] + 1] = -hg * J[i, j])
            end
            mpos = _SP.lu_mass_positions(la.lu, mass)
            for i in 1:n
                v[mpos[i]] += mass[i]
            end
            @test v == _SP.lu_values(la.lu, W)
            alg = findall(iszero, mass)
            for i in alg, j in alg
                t = la.targets[i, j]
                @test S[i, j] ? v[t + 1] == -hg * J[i, j] : t == -1
            end
        end
    end

    @testset "column colouring" begin
        rng = Random.MersenneTwister(7)
        for n in (1, 5, 40, 120), density in (0.02, 0.1, 0.4)
            S = _sp_random_pattern(rng, n, density)
            colour = _SP.colour_columns(S)
            @test _SP.colouring_valid(S, colour)
            @test maximum(colour) >= maximum(count(view(S, i, :)) for i in 1:n)
            @test maximum(colour) <= n
            # One compressed difference per colour recovers a linear map on the pattern.
            A = zeros(n, n)
            for j in 1:n, i in 1:n
                S[i, j] && (A[i, j] = randn(rng))
            end
            R = zeros(n, n)
            for c in 1:maximum(colour)
                d = Float64[colour[j] == c ? 1.0 : 0.0 for j in 1:n]
                f = A * d
                for j in 1:n, i in 1:n
                    S[i, j] && colour[j] == c && (R[i, j] = f[i])
                end
            end
            @test R == A
        end
        tri = falses(9, 9)
        for i in 1:9, j in max(1, i - 1):min(9, i + 1)
            tri[i, j] = true
        end
        @test maximum(_SP.colour_columns(tri)) == 3
        bad = ones(Int, 9)
        @test !_SP.colouring_valid(tri, bad)
    end

    @testset "pattern and plan of the ring" begin
        n = 6
        flat = _sp_ring_model(n)
        r = _SP.export_model(flat, mktempdir(); settings = _SP.ExportSettings(t_end = 0.1,
            method = :ros2, linear_solver = :sparse))
        @test r.ok
        la = r.report["linearAlgebra"]
        @test la["linearSolver"] == "sparse" && la["jacobian"] == "symbolic"
        # a ring: each derivative reads itself and its two neighbours
        @test la["nnzJ"] == 3n
        @test la["patternAddedFromNumeric"] == 0
        @test la["patternAddedFromSymbolic"] == 0
        @test la["colours"] == 3
        @test la["pivotCheck"]["ok"]
        @test la["fillIn"] > 0 && la["nnzLU"] == la["nnzW"] + la["fillIn"]

        r = _SP.export_model(flat, mktempdir(); settings = _SP.ExportSettings(t_end = 0.1,
            method = :ros2, sparse_threshold = 4, symbolic_jacobian_limit = 1.0))
        la = r.report["linearAlgebra"]
        @test la["linearSolver"] == "sparse" && la["jacobian"] == "fd"
        @test la["fdDerivativeCalls"] == 4
        r = _SP.export_model(flat, mktempdir(); settings = _SP.ExportSettings(t_end = 0.1,
            method = :ros2))
        @test r.report["linearAlgebra"]["linearSolver"] == "dense"
        r = _SP.export_model(flat, mktempdir(); settings = _SP.ExportSettings(t_end = 0.1))
        @test r.report["linearAlgebra"] === nothing     # RK4 needs no Jacobian
        s = _SP.ExportSettings(Dict("linear_solver" => "Sparse", "jacobian" => "FD",
            "sparse_threshold" => 10, "symbolic_jacobian_limit" => 5))
        @test s.linear_solver === :sparse && s.jacobian === :fd && s.sparse_threshold == 10
        r = _SP.export_model(flat, mktempdir(); settings = _SP.ExportSettings(linear_solver = :lapack))
        @test !r.ok && "E110" in Set(d.code for d in r.diagnostics)
    end

    cc = Sys.which("gcc")
    if cc === nothing
        @info "export sparse: no gcc on PATH, the C checks are skipped"
    else
        @testset "generated C sparse LU against a dense solve" begin
            rng = Random.MersenneTwister(11)
            # (n, density) random ODE patterns; (nd, -na) a DAE with a zero diagonal, solved
            # through the row matching
            for (n, density) in ((1, 0.0), (9, 0.3), (40, 0.08), (72, 0.05), (6, -40))
                if density < 0
                    S, mass, J = _sp_random_dae(rng, n, -round(Int, density))
                    n = size(S, 1)
                    hg = 1.0e-3
                    lu = _SP.static_lu(S; rowmatch = _SP.row_matching(S, mass; Js = [J]).rowmatch)
                    @test _SP.lu_rows_permuted(lu) > 0
                else
                    S = _sp_random_pattern(rng, n, density)
                    lu = _SP.static_lu(S)
                    J, _ = _sp_random_w(rng, S, 0.0)
                    hg = 0.25
                    mass = ones(n)
                end
                W = LinearAlgebra.Diagonal(mass) .- hg .* J
                T = _SP.jacobian_targets(S, lu)
                dir = mktempdir()
                open(joinpath(dir, "model.h"), "w") do io
                    print(io, """
                    #define BG_NX $n
                    #define BG_SZ(n) ((n) > 0 ? (n) : 1)
                    #define BG_LU_NNZ $(_SP.lu_nnz(lu))
                    #define BG_LU_NUPD $(length(lu.upd))
                    typedef struct { double t; double x[BG_NX]; double jac[BG_LU_NNZ];
                                     double lu[BG_LU_NNZ]; double lu_inv[BG_NX];
                                     double lu_y[BG_NX]; } bg_model;
                    static const double bg_mass[BG_NX] = {$(join(repr.(mass), ", "))};
                    void bg_jacobian(const bg_model *m, double t, const double *x, double *J);
                    int bg_w_factor(bg_model *m, double hg);
                    void bg_w_solve(bg_model *m, double *b);
                    int bg_alg_factor(bg_model *m);
                    """)
                end
                dae = !all(isone, mass)
                open(joinpath(dir, "check.c"), "w") do io
                    println(io, "#include <math.h>\n#include <stdio.h>\n#include \"model.h\"")
                    entries = [(T[i, j], J[i, j]) for j in 1:n for i in 1:n if S[i, j]]
                    println(io, "void bg_jacobian(const bg_model *m, double t, const double *x, double *J) {")
                    println(io, "    (void)m; (void)t; (void)x;")
                    for (p, v) in entries
                        println(io, "    J[$p] = $(repr(v));")
                    end
                    println(io, "}")
                    _SP.emit_sparse_lu(io, lu; mass, project = dae)
                    # a DAE also solves bg_project's Newton matrix on the same tables:
                    # identity rows with right-hand side 0, the algebraic rows of J
                    println(io, """
                    int main(void) {
                        static bg_model m;
                        double b[BG_NX];
                        for (int i = 0; i < BG_NX; ++i) b[i] = 1.0 + i;
                        bg_jacobian(&m, m.t, m.x, m.jac);
                        if (bg_w_factor(&m, $(repr(hg))) != 0) { printf("pivot\\n"); return 1; }
                        bg_w_solve(&m, b);
                        for (int i = 0; i < BG_NX; ++i) printf("%.17g\\n", b[i]);
                    $(dae ? """
                        for (int i = 0; i < BG_NX; ++i) b[i] = bg_mass[i] != 0.0 ? 0.0 : 1.0 + i;
                        if (bg_alg_factor(&m) != 0) { printf("pivot\\n"); return 1; }
                        bg_w_solve(&m, b);
                        for (int i = 0; i < BG_NX; ++i) printf("%.17g\\n", b[i]);
                    """ : "")
                        return 0;
                    }""")
                end
                exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
                @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -I $dir $(joinpath(dir, "check.c")) -o $exe -lm`)
                x = parse.(Float64, split(strip(read(`$exe`, String))))
                @test length(x) == (dae ? 2n : n)
                @test isapprox(x[1:n], W \ collect(1.0:n); rtol = dae ? 1e-9 : 1e-11)
                if dae
                    r = [mass[i] != 0 ? 0.0 : 1.0 + (i - 1) for i in 1:n]
                    A = _SP.projection_matrix(J, mass)
                    @test _SP.projection_check(lu, [J], mass).ok
                    xp = x[n + 1:end]
                    @test isapprox(xp, A \ r; rtol = 1e-9)
                    @test all(xp[i] == 0.0 for i in 1:n if mass[i] != 0)     # Δx_d = 0
                    alg = findall(iszero, mass)
                    @test isapprox(xp[alg], J[alg, alg] \ r[alg]; rtol = 1e-9)
                end
            end
        end

        @testset "ROS2 ring: dense and sparse, symbolic and fd agree in C" begin
            n = 6
            flat = _sp_ring_model(n)
            harness = joinpath(_SP.RUNTIME_DIR, "alloc_check.c")
            ys = Dict{Tuple{Symbol,Symbol},Float64}()
            cxx = Sys.which("g++")
            for solver in (:dense, :sparse), jac in (:symbolic, :fd)
                dir = mktempdir()
                r = _SP.export_model(flat, dir; settings = _SP.ExportSettings(t_end = 0.1,
                    dt = 1e-3, method = :ros2, linear_solver = solver, jacobian = jac))
                @test r.ok
                src = joinpath(dir, "sources")
                model_h = read(joinpath(src, "model.h"), String)
                @test occursin("#define BG_SPARSE_LU", model_h) == (solver === :sparse)
                files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
                for f in files
                    @test success(`$cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -fno-math-errno -c $f -I $src -o $(joinpath(dir, "o.o"))`)
                end
                if cxx !== nothing
                    for f in files[1:2]
                        @test success(`$cxx -x c++ -std=c++17 -fsyntax-only -Wall -Werror -I $src $f`)
                    end
                end
                exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
                @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
                out = read(`$exe 1 100`, String)
                @test occursin("after instantiate 0", out)
                ys[(solver, jac)] = parse(Float64, match(r"y\[0\] = (\S+)", out).captures[1])
            end
            ref = ys[(:dense, :symbolic)]
            @test isfinite(ref) && abs(ref - 0.1 * n) > 0.01    # the ring has moved
            @test isapprox(ys[(:sparse, :symbolic)], ref; rtol = 1e-12)
            @test isapprox(ys[(:dense, :fd)], ref; rtol = 1e-6)
            @test isapprox(ys[(:sparse, :fd)], ys[(:dense, :fd)]; rtol = 1e-12)
        end

        @testset "dense bg_w_factor/bg_w_solve with row exchanges against a dense solve" begin
            # bg_solver.c's dense seam on random, non-dominant W = I - J (partial pivoting
            # exchanges rows at several steps). bg_jacobian is redirected to a test matrix.
            n = 6
            dir = mktempdir()
            r = _SP.export_model(_sp_ring_model(n), dir; settings = _SP.ExportSettings(t_end = 0.1,
                method = :ros2, linear_solver = :dense))
            src = joinpath(dir, "sources")
            rng = Random.MersenneTwister(5)
            for trial in 1:4
                J = randn(rng, n, n)
                open(joinpath(dir, "check.c"), "w") do io
                    println(io, "#include <stdio.h>\n#include \"model.h\"")
                    println(io, "static const double JT[$(n * n)] = {", join(repr.(vec(permutedims(J))), ", "), "};")
                    println(io, """
                    static void test_jacobian(const bg_model *m, double t, const double *x, double *J) {
                        (void)m; (void)t; (void)x;
                        for (int i = 0; i < $(n * n); ++i) J[i] = JT[i];
                    }
                    #define bg_jacobian test_jacobian
                    #include "bg_solver.c"
                    int main(void) {
                        static bg_model m;
                        double b[BG_NX];
                        for (int i = 0; i < BG_NX; ++i) b[i] = 1.0 + i;
                        bg_jacobian(&m, m.t, m.x, m.jac);
                        if (bg_w_factor(&m, 1.0) != 0) { printf("singular\\n"); return 1; }
                        bg_w_solve(&m, b);
                        for (int i = 0; i < BG_NX; ++i) printf("%.17g\\n", b[i]);
                        return 0;
                    }""")
                end
                exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
                @test success(`$cc -std=c99 -O2 -I $src $(joinpath(dir, "check.c")) $(joinpath(src, "model.c")) -o $exe -lm`)
                x = parse.(Float64, split(strip(read(`$exe`, String))))
                W = Matrix{Float64}(LinearAlgebra.I, n, n) .- J
                @test isapprox(x, W \ collect(1.0:n); rtol = 1e-10)
            end
        end

        @testset "ROS2 stiff masses: the dense LU exchanges rows and agrees with the sparse LU" begin
            n = 4
            flat = _sp_ring_model(n; block = _sp_masses_block(n))
            harness = joinpath(_SP.RUNTIME_DIR, "alloc_check.c")
            ys = Dict{Symbol,Float64}()
            for solver in (:dense, :sparse)
                dir = mktempdir()
                r = _SP.export_model(flat, dir; settings = _SP.ExportSettings(t_end = 0.1,
                    dt = 1e-3, method = :ros2, linear_solver = solver))
                @test r.ok
                @test r.report["linearAlgebra"]["pivotCheck"]["ok"]
                src = joinpath(dir, "sources")
                files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
                exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
                @test success(`$cc -std=c11 -O2 -I $src $harness $files -o $exe -lm`)
                out = read(`$exe 1 100`, String)
                ys[solver] = parse(Float64, match(r"y\[0\] = (\S+)", out).captures[1])
            end
            # four unit masses pushed by 1 N for 0.1 s: q ≈ t²/8 once the springs settle
            @test isapprox(ys[:sparse], 0.1^2 / 8; rtol = 0.05)
            @test isapprox(ys[:dense], ys[:sparse]; rtol = 1e-9)
        end
    end
end
