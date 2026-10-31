# Closed-form mode shapes of a uniform slender beam (assumed-modes method) for the flexible
# beam blocks `stdlib:planar/FlexibleBeam2D` and `stdlib:spatial/FlexibleBeam3D`.
#
# This is the shared interface with the 3D viewer, which renders the deformed beam from the
# recorded modal coordinates with exactly these shapes (same normalisation, same sign):
#
#   * beam frame: origin at end A (s = 0), axis along local +x to end B (s = L);
#     bending "y" is a deflection along local y (rotation about z), bending "z" a deflection
#     along local z (rotation about -y), torsion a rotation about x;
#   * w(s) = sum_n phi_n(s) eta_n (eta in m, phi dimensionless), theta(s) = sum_n psi_n(s) eta_n
#     (eta in rad);
#   * normalisation (1/L) int_0^L phi_n^2 ds = 1, so a bending mode has the modal mass rho A L
#     and a torsion mode rho I_p L;
#   * basis "clamped-free" (0): phi_n = cosh(b s) - cos(b s) - sigma_n (sinh(b s) - sin(b s)),
#     b = lambda_n / L, sigma_n = (sinh l - sin l)/(cosh l + cos l); psi_n = sqrt(2) sin((2n-1) pi s/(2L));
#   * basis "free-free" (1): phi_n = cosh(b s) + cos(b s) - sigma_n (sinh(b s) + sin(b s)),
#     sigma_n = (cosh l - cos l)/(sinh l - sin l) (elastic modes only); psi_n = sqrt(2) cos(n pi s/L);
#   * omega_n = lambda_n^2 sqrt(E I/(rho A L^4)) (bending), omega_n = k_n pi/L sqrt(G J_t/(rho I_p))
#     (torsion), k_n = (2n-1)/2 (clamped-free) or n (free-free).
#
# `xi = s/L` everywhere; `beam_dphi` is d(phi)/d(xi) (divide by L for d/ds).

"""The eigenvalues `lambda_n` (n = 1..3) of the clamped-free and free-free beam (Blevins)."""
const BEAM_LAMBDA = (
    (1.87510407, 4.69409113, 7.85475744),     # clamped-free
    (4.73004074, 7.85320462, 10.99560784),    # free-free (elastic modes)
)

"""The basis names in the order of the blocks' `basis` constant (0, 1)."""
const BEAM_BASES = ("clamped-free", "free-free")

_basis_index(basis::Integer) = (basis == 0 || basis == 1) ? Int(basis) :
    throw(ArgumentError("basis must be 0 (clamped-free) or 1 (free-free), got $basis"))
function _basis_index(basis::AbstractString)
    k = findfirst(==(basis), BEAM_BASES)
    k === nothing && throw(ArgumentError("unknown basis `$basis`; use $(join(BEAM_BASES, " or "))"))
    return k - 1
end
_basis_index(basis::Symbol) = _basis_index(String(basis))

function _mode_index(n::Integer)
    1 <= n <= 3 || throw(ArgumentError("mode number must be 1, 2 or 3, got $n"))
    return Int(n)
end

"""    beam_lambda(basis, n) -> Float64

`lambda_n` of the bending mode `n` (1..3) in `basis` (0/"clamped-free" or 1/"free-free")."""
beam_lambda(basis, n::Integer) = BEAM_LAMBDA[_basis_index(basis) + 1][_mode_index(n)]

"""    beam_sigma(basis, n) -> Float64

The shape coefficient `sigma_n` of the bending mode."""
function beam_sigma(basis, n::Integer)
    l = beam_lambda(basis, n)
    return _basis_index(basis) == 0 ? (sinh(l) - sin(l)) / (cosh(l) + cos(l)) :
           (cosh(l) - cos(l)) / (sinh(l) - sin(l))
end

"""    beam_phi(basis, n, xi) -> Float64

The bending mode shape `phi_n` at `xi = s/L` (dimensionless, `int_0^1 phi^2 dxi = 1`)."""
function beam_phi(basis, n::Integer, xi::Real)
    l = beam_lambda(basis, n)
    s = beam_sigma(basis, n)
    x = l * xi
    return _basis_index(basis) == 0 ? cosh(x) - cos(x) - s * (sinh(x) - sin(x)) :
           cosh(x) + cos(x) - s * (sinh(x) + sin(x))
end

"""    beam_dphi(basis, n, xi) -> Float64

The slope `d phi_n / d xi` at `xi = s/L` (the slope in rad per unit eta is this over `L`)."""
function beam_dphi(basis, n::Integer, xi::Real)
    l = beam_lambda(basis, n)
    s = beam_sigma(basis, n)
    x = l * xi
    return _basis_index(basis) == 0 ? l * (sinh(x) + sin(x) - s * (cosh(x) - cos(x))) :
           l * (sinh(x) - sin(x) - s * (cosh(x) + cos(x)))
end

"""    torsion_k(basis, n) -> Float64

`k_n` of the torsion mode: `(2n-1)/2` (clamped-free) or `n` (free-free)."""
torsion_k(basis, n::Integer) =
    _basis_index(basis) == 0 ? (2 * _mode_index(n) - 1) / 2 : Float64(_mode_index(n))

"""    torsion_psi(basis, n, xi) -> Float64

The torsion mode shape `psi_n` at `xi = s/L` (`int_0^1 psi^2 dxi = 1`)."""
function torsion_psi(basis, n::Integer, xi::Real)
    k = torsion_k(basis, n)
    return _basis_index(basis) == 0 ? sqrt(2.0) * sin(k * pi * xi) : sqrt(2.0) * cos(k * pi * xi)
end

"""    torsion_dpsi(basis, n, xi) -> Float64

`d psi_n / d xi` at `xi = s/L`."""
function torsion_dpsi(basis, n::Integer, xi::Real)
    k = torsion_k(basis, n)
    return _basis_index(basis) == 0 ? sqrt(2.0) * k * pi * cos(k * pi * xi) :
           -sqrt(2.0) * k * pi * sin(k * pi * xi)
end

"""    bending_omega(basis, n; E, I, rho, A, L) -> Float64

Bending eigenfrequency (rad/s) `lambda_n^2 sqrt(E I / (rho A L^4))`."""
bending_omega(basis, n::Integer; E, I, rho, A, L) =
    beam_lambda(basis, n)^2 * sqrt(E * I / (rho * A * L^4))

"""    torsion_omega(basis, n; G, Jt, rho, Ip, L) -> Float64

Torsion eigenfrequency (rad/s) `k_n pi / L sqrt(G J_t / (rho I_p))`."""
torsion_omega(basis, n::Integer; G, Jt, rho, Ip, L) =
    torsion_k(basis, n) * pi / L * sqrt(G * Jt / (rho * Ip))

# 64-point Gauss-Legendre on [0, 1], composite over `m` panels: the mode integrals below are
# smooth (hyperbolic/trigonometric), so 32 panels give them to round-off.
function _gl_nodes(n::Int)
    x = zeros(n)
    w = zeros(n)
    for i in 1:n
        z = cos(pi * (i - 0.25) / (n + 0.5))
        for _ in 1:100
            p1, p2 = 1.0, 0.0
            for j in 1:n
                p3 = p2
                p2 = p1
                p1 = ((2j - 1) * z * p2 - (j - 1) * p3) / j
            end
            pp = n * (z * p1 - p2) / (z * z - 1)
            z1 = z
            z = z1 - p1 / pp
            abs(z - z1) < 1e-15 && break
        end
        p1, p2 = 1.0, 0.0
        for j in 1:n
            p3 = p2
            p2 = p1
            p1 = ((2j - 1) * z * p2 - (j - 1) * p3) / j
        end
        pp = n * (z * p1 - p2) / (z * z - 1)
        x[i] = z
        w[i] = 2 / ((1 - z * z) * pp * pp)
    end
    return x, w
end

"""    mode_integral(f; panels = 32) -> Float64

`int_0^1 f(xi) dxi` by composite Gauss-Legendre (64 points per panel)."""
function mode_integral(f; panels::Int = 32)
    x, w = _gl_nodes(64)
    h = 1.0 / panels
    s = 0.0
    for p in 0:(panels - 1)
        a = p * h
        for i in eachindex(x)
            s += w[i] * (h / 2) * f(a + (x[i] + 1) * h / 2)
        end
    end
    return s
end

"""
    beam_mode_tables(basis) -> NamedTuple

The dimensionless modal integrals the flexible beam blocks use, for modes 1..3 of `basis`
(`xi = s/L`, `'` = d/dxi):

  * `a[i] = int phi_i`, `b[i] = int xi phi_i` (first moments: the rigid/elastic coupling);
  * `phi0`, `phiL`, `dphi0`, `dphiL`: values and slopes at the ends;
  * `G0[i,j] = int phi_i' phi_j'` (foreshortening of the tip), `G1[i,j] = int (1 - xi) phi_i' phi_j'`
    (axial load of a uniform field, gravity), `G2[i,j] = int (1 - xi^2)/2 phi_i' phi_j'`
    (centrifugal axial load); `G2[1,1]` of the clamped-free basis is the Southwell coefficient
    1.193 of the first cantilever mode;
  * torsion: `at[j] = int psi_j`, `psi0`, `psiL`.
"""
function beam_mode_tables(basis)
    r = 1:3
    phi(i) = xi -> beam_phi(basis, i, xi)
    dphi(i) = xi -> beam_dphi(basis, i, xi)
    return (
        lambda = [beam_lambda(basis, i) for i in r],
        a = [mode_integral(phi(i)) for i in r],
        b = [mode_integral(xi -> xi * beam_phi(basis, i, xi)) for i in r],
        phi0 = [beam_phi(basis, i, 0.0) for i in r],
        phiL = [beam_phi(basis, i, 1.0) for i in r],
        dphi0 = [beam_dphi(basis, i, 0.0) for i in r],
        dphiL = [beam_dphi(basis, i, 1.0) for i in r],
        G0 = [mode_integral(xi -> dphi(i)(xi) * dphi(j)(xi)) for i in r, j in r],
        G1 = [mode_integral(xi -> (1 - xi) * dphi(i)(xi) * dphi(j)(xi)) for i in r, j in r],
        G2 = [mode_integral(xi -> (1 - xi^2) / 2 * dphi(i)(xi) * dphi(j)(xi)) for i in r, j in r],
        k = [torsion_k(basis, i) for i in r],
        at = [mode_integral(xi -> torsion_psi(basis, i, xi)) for i in r],
        psi0 = [torsion_psi(basis, i, 0.0) for i in r],
        psiL = [torsion_psi(basis, i, 1.0) for i in r],
    )
end
