# Work package J-MB3: the Lie-group / screw core (plan MULTIBOND section 6, D-MB2/D-MB3).
#
# Acceptance (the numbers are asserted, not skipped):
#   * `Ad(g1 ∘ g2) == Ad(g1) Ad(g2)` for random SE(2)/SE(3) poses, relative 1e-9;
#   * `ad(V)` is the central finite difference of `Ad(exp(V t))` at `t = 0`, 1e-6;
#   * the planar `Ad`/`ad` are the spatial ones restricted to the plane;
#   * `ad(V) V == 0` and `Vᵀ ad(V)ᵀ P == 0` (the gyrator power test), both dimensions;
#   * `exp`/`log` round-trip on random poses including θ ≈ 0 and θ ≈ π (SE3) and θ ≈ 2π
#     (SE2), 1e-9; `log(exp(T)) ≈ T` for small twists;
#   * the quaternion norm stays 1 after 1e5 random compositions (1e-12), and quaternion
#     composition/rotation agree with the matrix ones;
#   * the spatial inertia is symmetric positive definite, satisfies the parallel-axis
#     identity and restricts to the planar one, and a non-physical one is refused;
#   * the screw bases match plan 3.1 and reproduce the point velocity;
#   * the whitelist rows exist with the spec's arities, and the opaque registered functions
#     compile and solve through a real MTK `System` (the derivative probe of NOTES.md).

using Test
using BGSim
using BGSim: SourceRange, LowerCtx, Lit, VectorLit, MatrixLit, Name, Call,
    lower_expression
using ModelingToolkit
using ModelingToolkit: t_nounits as t, D_nounits as D
using OrdinaryDiffEqRosenbrock
using Symbolics
using StaticArrays
using LinearAlgebra

const compose = BGSim.Mech.compose  # ModelingToolkit also exports `compose`

# ---------------------------------------------------------------------------------------
# A deterministic pseudo-random stream (the test target has no Random dependency, and a
# fixed stream keeps a failure reproducible).
# ---------------------------------------------------------------------------------------

mutable struct _Stream
    s::UInt64
end
_Stream(seed::Integer) = _Stream(UInt64(seed))

function _next!(g::_Stream)
    g.s = g.s * 2862933555777941757 + 3037000493
    return g.s
end

"Uniform in [0, 1)."
_u(g::_Stream) = Float64(_next!(g) >> 11) / 9007199254740992.0
_uf(g::_Stream, a::Real, b::Real) = a + (b - a) * _u(g)
"Uniform in [-1, 1)."
_sf(g::_Stream) = _uf(g, -1.0, 1.0)

"An approximately unit 3-vector."
function _axis(g::_Stream)
    while true
        v = SVector(_sf(g), _sf(g), _sf(g))
        n = norm(v)
        n > 0.2 && return v / n
    end
end

_twist3(g::_Stream; wmax = 2.0, vmax = 2.0) = Twist{3}(
    _uf(g, -wmax, wmax), _uf(g, -vmax, vmax), _uf(g, -vmax, vmax)
)

function _twist6(g::_Stream; wmax = 2.0, vmax = 2.0)
    a = _uf(g, 0.0, wmax) * _axis(g)
    return Twist{6}(a[1], a[2], a[3], _uf(g, -vmax, vmax), _uf(g, -vmax, vmax),
        _uf(g, -vmax, vmax))
end

_pose2(g::_Stream) = SE2(_uf(g, -3.0, 3.0), SVector(_uf(g, -2.0, 2.0), _uf(g, -2.0, 2.0)))
_pose3(g::_Stream) = exp(_twist6(g))
_unit_quat(g::_Stream) = quat_exp(_uf(g, -π, π) * _axis(g))

"The pose/twist as a flat vector, so one norm-based tolerance works for all values."
_relvec(x::SE2) = SVector(cos(x.θ), sin(x.θ), x.p[1], x.p[2])
_relvec(x::SE3) = vcat(vec(collect(x.R)), collect(x.p))
_relvec(x::Quat) = SVector(x.w, x.x, x.y, x.z)
_relvec(x) = collect(Float64, x)

"True when `a` and `b` agree to `rtol` relative to their own norm (plus a small floor)."
function _relclose(a, b; rtol = 1e-9, atol = 1e-12)
    x = _relvec(a)
    y = _relvec(b)
    return norm(x - y) <= rtol * max(norm(x), norm(y)) + atol
end

"Embed a planar twist `[ω, vx, vy]` in the spatial `[ωx, ωy, ωz, vx, vy, vz]`."
_embed(V::Twist{3}) = Twist{6}(0.0, 0.0, V[1], V[2], V[3], 0.0)

"The rotation block of a planar pose, embedded as a rotation about z."
_embed_rotation(g::SE2) = SMatrix{3,3}(cos(g.θ), sin(g.θ), 0.0, -sin(g.θ), cos(g.θ), 0.0,
    0.0, 0.0, 1.0)

"The indices of the planar subalgebra in the spatial ordering (ωz, vx, vy)."
const PLANAR_IDX = [3, 4, 5]

@testset "J-MB3 Lie core" begin
    # -----------------------------------------------------------------------------------
    @testset "ordering, hat/vee and the adjoint identities" begin
        # Angular-first: the twist `[ω; v]` and the wrench `[m; f]` are separate types.
        V = Twist{6}(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        W = Wrench{6}(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        @test V isa AbstractVector{Float64}
        @test length(V) == 6 && V[4] == 4.0
        @test V + V == Twist{6}(2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
        @test 2.0 * V == V * 2.0
        @test norm(V) ≈ sqrt(91.0)
        @test collect(V) == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        @test SVector(V) === V.v
        @test_throws MethodError Twist{3}(1.0, 2.0)
        @test_throws ArgumentError Twist{3}([1.0, 2.0])
        @test_throws ArgumentError V + W  # a twist and a wrench do not mix

        # hat/vee round-trip for both dimensions.
        for V in (Twist{3}(0.3, 1.0, -2.0), Twist{6}(0.3, -0.2, 0.1, 1.0, 2.0, -1.0))
            @test vee(hat(V)) ≈ V
            @test hat(vee(hat(V))) ≈ hat(V)
        end
        # The planar hat is the `se(2)` matrix of plan 3.1.
        V3 = Twist{3}(0.3, 1.0, -2.0)
        @test hat(V3) == [0.0 -0.3 1.0; 0.3 0.0 -2.0; 0.0 0.0 0.0]
        @test hat(V3)[1:2, 1:2] == [0.0 -V3[1]; V3[1] 0.0]

        # `Ad(g1 ∘ g2) == Ad(g1) Ad(g2)`, relative 1e-9.
        g = _Stream(20261027)
        for _ in 1:64
            g1, g2 = _pose2(g), _pose2(g)
            @test _relclose(Ad(compose(g1, g2)), Ad(g1) * Ad(g2))
            @test _relclose(Ad(g1 * g2), Ad(g1) * Ad(g2))
            h1, h2 = _pose3(g), _pose3(g)
            @test _relclose(Ad(compose(h1, h2)), Ad(h1) * Ad(h2))
            @test _relclose(Ad(h1) * Ad(inv(h1)), Matrix(Ad(SE3())))
            @test _relclose(Ad(inv(h1)), inv(Ad(h1)))
        end

        # `Ad(g)` maps a body twist to the base frame, so `dot(W, V)` is frame invariant
        # with the dual rule `W -> AdDual(g) W = Ad(inv(g))' W`.
        h = _pose3(g)
        V6 = _twist6(g)
        W6 = Wrench{6}(SVector{6}(V6.v))
        @test dot(W6, V6) ≈ dot(AdDual(h) * W6, Ad(h) * V6) rtol = 1e-12
        @test Matrix(AdDual(h)) ≈ transpose(Ad(inv(h)))
        @test size(AdDual(h)) == (6, 6)
        # The twist rule applied to a wrench is a silent error, so it throws and points at
        # the dual; the dual applied to a twist is not a thing at all.
        @test_throws ArgumentError Ad(h) * W6
        @test_throws ArgumentError ad(V6) * W6
        @test_throws MethodError AdDual(h) * V6
        @test_throws ArgumentError Diagonal(ones(6)) * W6
        @test_throws ArgumentError hcat(Ad(h)[:, 1], Ad(h)[:, 2]) * W6
        # A matrix assembled by hand is applied to a wrench explicitly, through `.v`.
        @test Wrench(transpose(Ad(inv(h))) * W6.v) ≈ AdDual(h) * W6
    end

    # -----------------------------------------------------------------------------------
    @testset "ad is the derivative of Ad(exp(V t))" begin
        g = _Stream(7)
        h = 1e-6
        for _ in 1:32
            V = _twist3(g)
            fd = (Ad(exp(h * V)) - Ad(exp(-h * V))) / (2h)
            # Step-relative: a wrong entry of order 1e-6 must fail, a rounding-limited
            # central difference must pass (measured 1.3e-12 for the planar 3x3).
            @test maximum(abs, fd - ad(V)) <= 1e-9 * max(1.0, norm(ad(V)))
            # The second-order term of `Ad(exp(hV))` is `h² ad(V)² / 2`.
            @test _relclose(Ad(exp(h * V)),
                Matrix(Ad(SE2())) + h * ad(V) + h^2 / 2 * ad(V)^2; rtol = 1e-9)
            U = _twist6(g)
            fd6 = (Ad(exp(h * U)) - Ad(exp(-h * U))) / (2h)
            @test maximum(abs, fd6 - ad(U)) <= 1e-9 * max(1.0, norm(ad(U)))
        end
    end

    # -----------------------------------------------------------------------------------
    @testset "planar Ad/ad are the spatial restriction" begin
        g = _Stream(11)
        for _ in 1:32
            g2 = _pose2(g)
            A3 = Ad(g2)
            A6 = Ad(SE3(_embed_rotation(g2), SVector(g2.p[1], g2.p[2], 0.0)))
            @test _relclose(A6[PLANAR_IDX, PLANAR_IDX], A3)
            # ... and on the twists: `Ad(embed(g)) * embed(V) == embed(Ad(g) * V)`.
            V3 = _twist3(g)
            @test _relclose((A6 * _embed(V3))[PLANAR_IDX], A3 * V3)
            @test maximum(abs, (A6 * _embed(V3))[[1, 2, 6]]) < 1e-15

            U3 = _twist3(g)
            @test _relclose(ad(_embed(U3))[PLANAR_IDX, PLANAR_IDX], ad(U3))
            W3 = _twist3(g)
            @test _relclose((ad(_embed(U3)) * _embed(W3))[PLANAR_IDX], ad(U3) * W3)
        end
    end

    # -----------------------------------------------------------------------------------
    @testset "ad(V) V = 0 and the gyrator power Vᵀ ad(V)ᵀ P = 0" begin
        g = _Stream(13)
        for _ in 1:64
            V3 = _twist3(g)
            P3 = Wrench{3}(SVector{3}(_twist3(g).v))
            @test maximum(abs, ad(V3) * V3) < 1e-15
            @test abs(dot(V3, Wrench(transpose(ad(V3)) * P3.v))) <=
                  1e-9 * norm(V3) * norm(ad(V3)) * norm(P3)
            V6 = _twist6(g)
            P6 = Wrench{6}(SVector{6}(_twist6(g).v))
            @test maximum(abs, ad(V6) * V6) < 1e-15
            @test abs(dot(V6, Wrench(transpose(ad(V6)) * P6.v))) <=
                  1e-9 * norm(V6) * norm(ad(V6)) * norm(P6)
        end
        # The planar formula of plan 3.1, entry by entry.
        ω, vx, vy = 0.4, -1.2, 2.5
        @test ad(Twist{3}(ω, vx, vy)) == [0.0 0.0 0.0; vy 0.0 -ω; -vx ω 0.0]
    end

    # -----------------------------------------------------------------------------------
    @testset "SE2 exp/log" begin
        g = _Stream(17)
        for _ in 1:64
            g2 = _pose2(g)
            back = exp(log(g2))
            @test _relclose(rotation(back), rotation(g2))
            @test _relclose(translation(back), translation(g2))

            T = Twist{3}(_uf(g, -0.5, 0.5), _uf(g, -1.0, 1.0), _uf(g, -1.0, 1.0))
            @test _relclose(log(exp(T)), T)
        end
        # θ near 0: the small-angle branch and the series of `V(θ)`.
        for θ in (0.0, 1e-12, 1e-9, 1e-6, 1e-4, 1e-3, 1e-2, -1e-3, 1e-2 + 1e-12)
            g2 = SE2(θ, SVector(0.7, -0.3))
            @test _relclose(exp(log(g2)), g2)
            @test isfinite(log(g2)[1])
            @test _relclose(translation(exp(log(g2))), SVector(0.7, -0.3))
        end
        # θ near 2π (and near -2π): the same rotation as θ ≈ 0; `log` folds the angle into
        # the principal range before inverting `V(θ)`, which is singular at 2π.
        for θ in (2π - 1e-9, 2π - 1e-6, 2π - 1e-3, 2π + 1e-7, -2π + 1e-9, -2π - 1e-5)
            for p in (SVector(0.0, 0.0), SVector(1.0, -2.0), SVector(-3.0, 0.5))
                g2 = SE2(θ, p)
                @test _relclose(exp(log(g2)), g2)
            end
        end
        # θ = π exactly (the branch boundary).
        g2 = SE2(π, SVector(1.0, 2.0))
        @test _relclose(exp(log(g2)), g2)
        @test abs(abs(log(g2)[1]) - π) < 1e-12
    end

    # -----------------------------------------------------------------------------------
    @testset "SE3 exp/log (Rodrigues, near 0 and near π)" begin
        g = _Stream(19)
        for _ in 1:64
            h = _pose3(g)
            back = exp(log(h))
            @test _relclose(rotation(back), rotation(h))
            @test _relclose(translation(back), translation(h))

            T = Twist{6}(_uf(g, -0.5, 0.5), _uf(g, -0.5, 0.5), _uf(g, -0.5, 0.5),
                _uf(g, -1.0, 1.0), _uf(g, -1.0, 1.0), _uf(g, -1.0, 1.0))
            @test _relclose(log(exp(T)), T)
        end
        # Angles at and around 0 and π, every branch of Shepperd's method.
        for θ in (0.0, 1e-12, 1e-9, 1e-6, 1e-4, 1e-2, π - 1e-9, π - 1e-6, π - 1e-3, π)
            for axis in (SVector(1.0, 0.0, 0.0), SVector(0.0, 1.0, 0.0),
                SVector(0.0, 0.0, 1.0), SVector(1.0, 1.0, 0.0) / sqrt(2),
                SVector(-1.0, 2.0, -3.0) / sqrt(14.0))
                V = Twist{6}(θ * axis[1], θ * axis[2], θ * axis[3], 0.5, -1.0, 2.0)
                h = exp(V)
                back = exp(log(h))
                @test _relclose(rotation(back), rotation(h))
                @test _relclose(translation(back), translation(h))
            end
        end
        # `exp(hat(V))` is the 4x4 homogeneous matrix of the same pose.
        T = Twist{6}(0.3, -0.2, 0.1, 1.0, 2.0, -1.0)
        H = exp(T)
        E = exp(hat(T))
        @test E[1:3, 1:3] ≈ rotation(H)
        @test E[1:3, 4] ≈ translation(H)
        @test E[4, :] == [0.0, 0.0, 0.0, 1.0]

        # Pose construction validates: a matrix that is not a rotation is refused.
        @test_throws ArgumentError SE3(zeros(3, 3), SVector(0.0, 0.0, 0.0))
        @test_throws ArgumentError SE3(SMatrix{3,3}(1.0, 0.0, 0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, -1.0), SVector(0.0, 0.0, 0.0))
        @test_throws ArgumentError SE3(2.0 * rotation(H), SVector(0.0, 0.0, 0.0))
    end

    # -----------------------------------------------------------------------------------
    @testset "quaternions" begin
        g = _Stream(23)
        q = _unit_quat(g)
        @test abs(BGSim.Mech.quat_norm(q) - 1) < 1e-15
        @test quat_rotate(q, SVector(1.0, 0.0, 0.0)) ≈
              quat_to_matrix(q) * SVector(1.0, 0.0, 0.0)

        # 1e5 random compositions: the norm stays 1 to 1e-12.
        acc = Quat()
        worst = 0.0
        for _ in 1:100_000
            acc = compose(acc, _unit_quat(g))
            worst = max(worst, abs(BGSim.Mech.quat_norm(acc) - 1))
        end
        @test worst < 1e-12
        @test abs(BGSim.Mech.quat_norm(acc) - 1) < 1e-12

        # Composition agrees with the matrix product; the inverse is the conjugate.
        a, b = _unit_quat(g), _unit_quat(g)
        @test quat_to_matrix(compose(a, b)) ≈ quat_to_matrix(a) * quat_to_matrix(b)
        ident = compose(a, inv(a))
        @test abs(ident.w - 1) < 1e-15
        @test norm(SVector(ident.x, ident.y, ident.z)) < 1e-15
        @test quat_rotate(compose(a, b), SVector(0.3, -0.2, 0.5)) ≈
              quat_rotate(a, quat_rotate(b, SVector(0.3, -0.2, 0.5)))

        # quaternion -> matrix -> quaternion round-trip (up to the sign of q).
        for _ in 1:64
            u = _unit_quat(g)
            u2 = quat_from_rotation(quat_to_matrix(u))
            @test _relclose(quat_to_matrix(u2), quat_to_matrix(u))
            @test abs(BGSim.Mech.quat_norm(u2) - 1) < 1e-15
        end

        # Rotation-vector exp/log, including the principal branch at π.
        for θ in (0.0, 1e-12, 1e-6, 0.3, π / 2, π - 1e-9, π)
            v = θ * _axis(g)
            @test _relclose(quat_log(quat_exp(v)), v)
        end
        @test_throws ArgumentError normalise(Quat(0.0, 0.0, 0.0, 0.0))
        @test_throws ArgumentError inv(Quat(0.0, 0.0, 0.0, 0.0))
        @test_throws ArgumentError quat_from_rotation(zeros(3, 3))
        @test _relclose(exp(Quat(0.0, 1.0, 0.0, 0.0)), Quat(cos(1.0), sin(1.0), 0.0, 0.0))
        @test _relclose(log(Quat(cos(1.0), sin(1.0), 0.0, 0.0)), Quat(0.0, 1.0, 0.0, 0.0))
    end

    # -----------------------------------------------------------------------------------
    @testset "spatial inertia" begin
        g = _Stream(29)
        m = 2.5
        J = SVector(0.4, 0.7, 1.1)
        for _ in 1:16
            c = SVector(_uf(g, -0.5, 0.5), _uf(g, -0.5, 0.5), _uf(g, -0.5, 0.5))
            M = spatial_inertia(m, J, c)
            # symmetric and positive definite
            @test M == transpose(M)
            @test isposdef(Symmetric(M))
            @test isposdef(Symmetric(M[1:3, 1:3]))
            # One tolerance for the symmetry of a physical inertia: a one-sided asymmetry at
            # the rounding level (1e-13) is accepted by both the validator and the builder...
            Meps = Matrix(M)
            Meps[1, 2] += 1e-13
            @test validate_inertia(SMatrix{6,6}(Meps)) !== nothing
            @test validate_inertia(SMatrix{3,3}(Meps[1:3, 1:3])) !== nothing
            Ic = Matrix(SMatrix{3,3}(M[1:3, 1:3]))
            Iceps = copy(Ic)
            Iceps[1, 2] += 1e-13
            @test spatial_inertia(m, SMatrix{3,3}(Iceps), c) isa SMatrix{6,6}
            # ... and a real asymmetry is refused by both.
            Mbad = Matrix(M)
            Mbad[1, 2] += 1e-6
            @test_throws ArgumentError validate_inertia(SMatrix{6,6}(Mbad))
            Icbad = copy(Ic)
            Icbad[1, 2] += 1e-6
            @test_throws ArgumentError spatial_inertia(m, SMatrix{3,3}(Icbad), c)
            # A 1e-13 asymmetry is inside the tolerance, a 1e-6 one is not: the *same*
            # `rtol` decides both, so the two functions cannot disagree.
            @test BGSim.Mech.INERTIA_RTOL == 1e-12

            # the formula of plan 3.1, block by block
            C = skew(c)
            @test M[1:3, 1:3] ≈ Diagonal(J) + m * (C * transpose(C))
            @test M[1:3, 4:6] ≈ m * C
            @test M[4:6, 1:3] ≈ m * transpose(C)
            @test M[4:6, 4:6] ≈ m * I

            # parallel-axis theorem for an arbitrary axis through the origin
            a = _axis(g)
            @test dot(a, M[1:3, 1:3] * a) ≈
                  dot(a, Diagonal(J) * a) + m * (dot(c, c) - dot(a, c)^2) rtol = 1e-14

            # With the CoM at the origin the inertia is `diag(J, m I)` (D-MB3).
            @test spatial_inertia(m, J) ≈ [Diagonal(J) zeros(3, 3); zeros(3, 3) m * I]
            @test spatial_inertia(m, J, zero(c)) ≈ spatial_inertia(m, J)

            # Planar restriction: (ωz, vx, vy) of the 3D body with Ic = diag(J) and
            # c = (cx, cy, 0) is the planar inertia of D-MB3.
            M2 = planar_inertia(m, J[3], SVector(c[1], c[2]))
            M6 = spatial_inertia(m, J, SVector(c[1], c[2], 0.0))
            @test M6[PLANAR_IDX, PLANAR_IDX] ≈ M2
            # ... and at the CoM the v1 case is `diag(J, m, m)`.
            @test planar_inertia(m, J[3]) ≈ [J[3] 0.0 0.0; 0.0 m 0.0; 0.0 0.0 m]
        end
        # Kinetic energy `V' M V / 2` is positive for a non-zero twist.
        M = spatial_inertia(m, J, SVector(0.1, -0.2, 0.3))
        for _ in 1:16
            V = _twist6(g)
            @test dot(V, M * V) > 0
        end

        # No silent acceptance of an unphysical inertia.
        @test_throws ArgumentError spatial_inertia(-1.0, J)
        @test_throws ArgumentError spatial_inertia(0.0, J)
        @test_throws ArgumentError spatial_inertia(m, SVector(0.4, -0.7, 1.1))
        @test_throws ArgumentError spatial_inertia(m, SVector(0.0, 0.0, 1.0))
        @test_throws ArgumentError spatial_inertia(m,
            [1.0 0.0 0.0; 0.0 -1.0 0.0; 0.0 0.0 1.0])
        @test_throws ArgumentError spatial_inertia(m,
            [1.0 0.3 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0])
        @test_throws ArgumentError planar_inertia(-2.0, 1.0)
        @test_throws ArgumentError planar_inertia(1.0, -1.0)
        @test_throws ArgumentError validate_inertia(zeros(6, 6))
        @test_throws ArgumentError validate_inertia(zeros(4, 4))
        # `validate_inertia` returns the matrix it accepted.
        @test validate_inertia(M) === M
    end

    # -----------------------------------------------------------------------------------
    @testset "screw bases and point velocity" begin
        # Plan 3.1: the planar revolute screw of a joint through `r` is `[1, r_y, -r_x]`.
        for _ in 1:16
            r2 = SVector(0.7, -1.3)
            S = revolute_screw(r2)
            @test S == Twist{3}(1.0, r2[2], -r2[1])
            # The same joint written in the spatial (D = 6) form.
            @test revolute_screw(SVector(0.0, 0.0, 1.0), SVector(r2[1], r2[2], 0.0)) ==
                  Twist{6}(0.0, 0.0, 1.0, r2[2], -r2[1], 0.0)
        end
        # The screw reproduces the point velocity: with the twist `ω S` the velocity of a
        # point `p` is `ω × (p - r)`, equal to `v_origin + ω × p`.
        p = SVector(1.4, 0.6, 0.0)
        r = SVector(-0.5, 0.9, 0.0)
        ω = 1.7
        S = revolute_screw(SVector(0.0, 0.0, 1.0), r)
        V = ω * S
        ωvec = SVector(V[1], V[2], V[3])
        vorigin = SVector(V[4], V[5], V[6])
        @test vorigin + cross(ωvec, p) ≈ cross(ωvec, p - r) rtol = 1e-15
        @test vorigin ≈ cross(ωvec, -r) rtol = 1e-15

        # Prismatic: no rotation, pure translation along the (normalised) axis.
        @test prismatic_screw(SVector(0.0, 1.0, 0.0)) ==
              Twist{6}(0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        @test prismatic_screw(SVector(2.0, 0.0)) == Twist{3}(0.0, 1.0, 0.0)
        # A non-unit axis is normalised, so the joint coordinate stays a displacement in
        # metres instead of being silently scaled by |axis|.
        @test prismatic_screw(SVector(0.0, 0.0, 3.0)) ==
              Twist{6}(0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        @test prismatic_screw(SVector(-2.0, 2.0)) == Twist{3}(0.0, -1 / sqrt(2), 1 / sqrt(2))
        @test prismatic_screw([0.0, -4.0]) == Twist{3}(0.0, 0.0, -1.0)
        @test prismatic_screw([0.0, 0.0, 5.0]) == Twist{6}(0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        @test_throws ArgumentError prismatic_screw(SVector(0.0, 0.0, 0.0))
        @test_throws ArgumentError prismatic_screw(SVector(0.0, 0.0))
        @test_throws ArgumentError prismatic_screw([0.0, 0.0])
        @test_throws ArgumentError screw(SVector(0.0, 0.0, 0.0), SVector(1.0, 2.0, 0.0))
        @test_throws ArgumentError revolute_screw(SVector(0.0, 0.0, 0.0),
            SVector(1.0, 2.0, 0.0))

        # Helical: `pitch` adds the axial translation to the origin velocity.
        a = SVector(0.0, 0.0, 1.0)
        r3 = SVector(1.0, 2.0, 0.0)
        h = screw(a, r3, 0.25)
        @test h[1:3] ≈ a
        @test h[4:6] ≈ collect(revolute_screw(a, r3))[4:6] + 0.25 * a
        # A non-unit axis is normalised.
        @test screw(SVector(0.0, 0.0, 2.0), r3, 0.25) ≈ h

        # The joint basis `S` is a `Mat{D,n}` whose columns are the screws (D-MB8).
        S1 = revolute_screw(SVector(0.0, 0.0, 1.0), r3)
        S2 = prismatic_screw(SVector(1.0, 0.0, 0.0))
        B = joint_basis(S1, S2)
        @test size(B) == (6, 2)
        @test B[:, 1] ≈ collect(S1)
        @test B[:, 2] ≈ collect(S2)
        B3 = joint_basis([revolute_screw(SVector(0.5, 0.2)),
            prismatic_screw(SVector(1.0, 0.0))])
        @test size(B3) == (3, 2)
        @test B3[:, 1] ≈ [1.0, 0.2, -0.5]
        @test_throws ArgumentError joint_basis(Twist{6}[])
    end

    # -----------------------------------------------------------------------------------
    @testset "whitelist rows (spec function additions)" begin
        # The base table is unchanged (one row per spec line of the M1 function table);
        # the spatial-mechanics additions live in their own table, as in the spec.
        @test length(BGSim.FUNCTION_RULES) == 24
        @test length(BGSim.MECH_FUNCTION_RULES) == 18
        for name in (:hat, :vee, :Ad, :ad, :compose, :inv, :spatial_inertia, :SE3,
            :rotation, :translation, :quat_compose, :quat_inv, :quat_normalise,
            :quat_exp, :quat_log, :quat_to_matrix, :quat_from_rotation, :quat_rotate)
            rule = BGSim.function_rule(name)
            @test rule !== nothing
            @test rule === BGSim.mech_function_rule(name)
            @test rule.lowering === :mech
            @test rule.contexts == BGSim.ALL_CONTEXTS
        end
        # `exp`/`log` keep the base row (they are overloaded on the argument shape).
        @test BGSim.function_rule(:exp).lowering === :math
        @test BGSim.function_rule(:log).lowering === :math
        @test BGSim.mech_function_rule(:exp) === nothing
        # Arity, as the spec writes it.
        @test BGSim.function_rule(:Ad).max_args == 1
        @test BGSim.function_rule(:spatial_inertia).min_args == 2
        @test BGSim.function_rule(:spatial_inertia).max_args == 3
        @test BGSim.function_rule(:compose).min_args == 2
        @test BGSim.function_rule(:SE3).min_args == 0
        @test BGSim.function_rule(:SE3).max_args == 2
        # Names that stay out of scope (MULTIBOND_PLAN section 12).
        @test BGSim.function_rule(:pose_of) === nothing
        @test BGSim.function_rule(:jacobian) === nothing

        # The checker accepts a mech row in the equation scope and reports the arity.
        pb = parse_block("""
        @block MechRow begin
            @parameters a::Real = 1.0
            @variables r::Real
            @equations r ~ inv(a) + Ad(a) + ad(a) + hat(a) + quat_normalise(a)
        end
        """)
        @test isempty([d for d in check_block(pb) if d.code in ("E001", "E002")])
        bad = parse_block("""
        @block MechArity begin
            @parameters a::Real = 1.0
            @variables r::Real
            @equations r ~ Ad(a, a)
        end
        """)
        @test any(d -> d.code == "E001" && occursin("`Ad` takes 1 argument", d.message),
            check_block(bad))
        # A near-miss is still E002 (the whitelist stays closed).
        miss = parse_block("""
        @block MechMiss begin
            @parameters a::Real = 1.0
            @variables r::Real
            @equations r ~ Adjoint(a)
        end
        """)
        @test any(d -> d.code == "E002" && occursin("Adjoint", d.message),
            check_block(miss))
    end

    # -----------------------------------------------------------------------------------
    @testset "lowering: the pose algebra builds the numeric core" begin
        R = SourceRange("", 1, 1, 1, 1)
        th = mtk_variable("mech.th")
        ctx = LowerCtx(Dict{String,Num}("th" => th), Dict{String,Num}())
        ast(x) = x isa Symbol ? Name(x, R) : Lit(x, R)
        vlit(xs) = VectorLit([ast(x) for x in xs], R)
        mlit(rows) = MatrixLit([[ast(x) for x in row] for row in rows], R)
        call(f, args) = Call(Name(f, R), args, R)
        low(e) = lower_expression(e, ctx)
        value(x) = (f = Symbolics.build_function(x, th; expression = Val(false));
                    (f isa Tuple ? first(f) : f)(0.4))

        θ = 0.4
        # Ad: the planar matrix, and the spatial `[[R, 0], [p̂R, R]]` of `exp`.
        @test value(low(call(:Ad, [vlit([:th, 1.0, 2.0])]))) ≈ Ad(SE2(θ, 1.0, 2.0))
        T = Twist{6}(θ, -0.2, 0.1, 1.0, 2.0, -1.0)
        h7call = call(:exp, [vlit([:th, -0.2, 0.1, 1.0, 2.0, -1.0])])
        @test length(low(h7call)) == 7
        @test value(low(call(:Ad, [h7call]))) ≈ Ad(exp(T)) rtol = 1e-13
        # ad / hat / vee.
        @test value(low(call(:ad, [vlit([:th, 1.0, 2.0])]))) ≈ ad(Twist{3}(θ, 1.0, 2.0))
        @test value(low(call(:ad, [vlit([:th, 1.0, 2.0, 3.0, 4.0, 5.0])]))) ≈
              ad(Twist{6}(θ, 1.0, 2.0, 3.0, 4.0, 5.0))
        @test value(low(call(:hat, [vlit([:th, 1.0, 2.0])]))) ≈ hat(Twist{3}(θ, 1.0, 2.0))
        @test value(low(call(:hat, [vlit([:th, 1.0, 2.0, 3.0, 4.0, 5.0])]))) ≈
              hat(Twist{6}(θ, 1.0, 2.0, 3.0, 4.0, 5.0))
        @test value(low(call(:vee, [mlit([[0.0, -1.0, 2.0], [1.0, 0.0, 3.0],
            [0.0, 0.0, 0.0]])]))) ≈ [1.0, 2.0, 3.0]
        # exp / log, planar and spatial (the pose chart is quaternion + position).
        @test value(low(call(:exp, [vlit([:th, 1.0, 2.0])]))) ≈
              BGSim.Mech.chart(exp(Twist{3}(θ, 1.0, 2.0)))
        @test value(low(h7call)) ≈ BGSim.Mech.chart(exp(T))
        @test value(low(call(:log, [vlit([:th, 1.0, 2.0])]))) ≈
              collect(log(SE2(θ, 1.0, 2.0)))
        h = exp(T)
        @test value(low(call(:log, [vlit(collect(BGSim.Mech.chart(h)))]))) ≈ collect(log(h))
        # compose / inv agree with the group operations at the sampled point.
        @test value(low(call(:compose, [vlit([:th, 1.0, 2.0]), vlit([0.3, -1.0, 0.5])]))) ≈
              BGSim.Mech.chart(compose(SE2(θ, 1.0, 2.0), SE2(0.3, -1.0, 0.5)))
        @test value(low(call(:inv, [vlit([:th, 1.0, 2.0])]))) ≈
              BGSim.Mech.chart(inv(SE2(θ, 1.0, 2.0)))
        # spatial inertia, planar and spatial.
        @test value(low(call(:spatial_inertia, [ast(2.0), ast(1.0), vlit([0.1, 0.2])]))) ≈
              planar_inertia(2.0, 1.0, SVector(0.1, 0.2))
        @test value(low(call(:spatial_inertia, [ast(2.0),
            mlit([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]]),
            vlit([0.1, 0.2, 0.3])]))) ≈
              spatial_inertia(2.0, SVector(1.0, 2.0, 3.0), SVector(0.1, 0.2, 0.3))
        @test value(low(call(:spatial_inertia, [ast(2.0), ast(1.0)]))) ≈
              planar_inertia(2.0, 1.0)
        # SE3 / rotation / translation.
        @test value(low(call(:SE3, []))) == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        Rz = mlit([[cos(θ), -sin(θ), 0.0], [sin(θ), cos(θ), 0.0], [0.0, 0.0, 1.0]])
        g7call = call(:SE3, [Rz, vlit([1.0, 2.0, 3.0])])
        Rref = SMatrix{3,3}(cos(θ), sin(θ), 0.0, -sin(θ), cos(θ), 0.0, 0.0, 0.0, 1.0)
        @test value(low(g7call)) ≈ BGSim.Mech.chart(SE3(Rref, SVector(1.0, 2.0, 3.0)))
        @test value(low(call(:rotation, [g7call]))) ≈ Rref
        @test value(low(call(:translation, [g7call]))) ≈ [1.0, 2.0, 3.0]
        # quaternion helpers.
        qcall = call(:quat_exp, [vlit([:th, 0.2, 0.3])])
        qref = quat_exp(SVector(θ, 0.2, 0.3))
        @test value(low(qcall)) ≈ [qref.w, qref.x, qref.y, qref.z] rtol = 1e-13
        @test value(low(call(:quat_to_matrix, [qcall]))) ≈ quat_to_matrix(qref)
        qq = compose(qref, qref)
        @test value(low(call(:quat_compose, [qcall, qcall]))) ≈ [qq.w, qq.x, qq.y, qq.z]
        @test value(low(call(:quat_inv, [qcall]))) ≈ [qref.w, -qref.x, -qref.y, -qref.z]
        @test value(low(call(:quat_log, [qcall]))) ≈ quat_log(qref) rtol = 1e-13
        qn = normalise(qref)
        @test value(low(call(:quat_normalise, [qcall]))) ≈ [qn.w, qn.x, qn.y, qn.z]
        @test value(low(call(:quat_rotate, [qcall, vlit([1.0, 0.0, 0.0])]))) ≈
              quat_rotate(qref, SVector(1.0, 0.0, 0.0))
        qR = quat_from_rotation(Rref)
        @test value(low(call(:quat_from_rotation, [Rz]))) ≈ [qR.w, qR.x, qR.y, qR.z]
        # A scalar `exp`/`log` keeps the ordinary meaning.
        @test value(low(call(:exp, [Name(:th, R)]))) ≈ exp(θ)
        @test value(low(call(:log, [Name(:th, R)]))) ≈ log(θ)
        # A wrong shape is a clear lowering error, not a silent value.
        @test_throws BGSim.LowerError low(call(:Ad, [vlit([1.0, 2.0])]))
        @test_throws BGSim.LowerError low(call(:hat, [mlit([[1.0, 0.0], [0.0, 1.0]])]))
    end

    # -----------------------------------------------------------------------------------
    @testset "registration: MTK compiles and solves through the opaque functions" begin
        w = mtk_variable("mech.w")
        e1 = mtk_variable("mech.e1")
        e2 = mtk_variable("mech.e2")
        e3 = mtk_variable("mech.e3")
        k = mtk_parameter("mech.k")
        # `bg_exp2` in the state derivative: the implicit solver's Jacobian must
        # differentiate the opaque call (with ForwardDiff duals, NOTES.md).
        eqs = [
            D(w) ~ -k * BGSim.bg_exp2(w, 1.0, 0.0, 2),
            e1 ~ BGSim.bg_exp2(w, 1.0, 0.5, 2),
            e2 ~ BGSim.bg_exp2(w, 1.0, 0.5, 3),
            e3 ~ sum(BGSim.bg_inertia3(2.0, 1.0, 2.0, 3.0, 0.1, 0.2, 0.3, j, j)
                     for j in 1:6),
        ]
        sys = mtkcompile(System(eqs, t, [w, e1, e2, e3], [k]; name = :mech_probe))
        prob = ODEProblem(sys, [w => 1.0, k => 1.0], (0.0, 0.5))
        sol = solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        @test sol.retcode == ReturnCode.Success
        # The observed values are exactly the numeric core's chart at the solved state.
        wend = sol(0.5, idxs = w)
        chart_end = BGSim.Mech.chart(exp(Twist{3}(wend, 1.0, 0.5)))
        @test sol(0.5, idxs = e1) ≈ chart_end[2] rtol = 1e-9
        @test sol(0.5, idxs = e2) ≈ chart_end[3] rtol = 1e-9
        @test sol(0.5, idxs = e3) ≈
              tr(spatial_inertia(2.0, SVector(1.0, 2.0, 3.0), SVector(0.1, 0.2, 0.3))) rtol = 1e-12
        # The derivative of an opaque registered call stays unevaluated: that is fine for
        # the *numerical* Jacobian (ForwardDiff through the generated code, the production
        # path) and is why `jac = true` is only used on the paths that expand symbolically
        # (see the next testset).
        d = Symbolics.derivative(BGSim.bg_exp2(w, 1.0, 0.0, 2), w)
        @test d isa Num
        @test occursin("Differential", string(d))
        # The quaternion algebra does NOT: a product of two state quaternions is plain
        # scalar arithmetic with no opaque call and a plain symbolic derivative.
        R = SourceRange("", 1, 1, 1, 1)
        cq = [mtk_variable("mech.cq$k") for k in 1:4]
        cr = [mtk_variable("mech.cr$k") for k in 1:4]
        ctxq = LowerCtx(Dict{String,Num}(), Dict{String,Num}())
        for k in 1:4
            ctxq.vars["cq$k"] = cq[k]
            ctxq.vars["cr$k"] = cr[k]
        end
        prod = lower_expression(Call(Name(:quat_compose, R),
            [VectorLit([Name(Symbol("cq$k"), R) for k in 1:4], R),
                VectorLit([Name(Symbol("cr$k"), R) for k in 1:4], R)], R), ctxq)
        @test !occursin("bg_quat", string(prod))
        dq = Symbolics.derivative(Symbolics.unwrap(prod[1]), Symbolics.unwrap(cq[2]))
        @test !occursin("Differential", string(dq))
        @test dq isa Num

        # The *lowered* pose algebra also goes through a real System: `Ad(g)` built by
        # `lower_mech` is a matrix of symbolic entries, and one of its entries is solved
        # here as a state function.
        ctxw = LowerCtx(Dict{String,Num}("w" => w), Dict{String,Num}())
        A = lower_expression(
            Call(Name(:Ad, R), [VectorLit([Name(:w, R), Lit(1.0, R), Lit(2.0, R)], R)], R),
            ctxw,
        )
        @test size(A) == (3, 3)
        ya = mtk_variable("mech.ya")
        sys2 = mtkcompile(System(
            [D(w) ~ 0.5, ya ~ A[2, 2]], t, [w, ya], []; name = :mech_ad
        ))
        sol2 = solve(ODEProblem(sys2, [w => 0.2], (0.0, 0.4)), Rodas5P();
            abstol = 1e-10, reltol = 1e-10)
        @test sol2.retcode == ReturnCode.Success
        # w(0.4) = 0.2 + 0.5 * 0.4 = 0.4 and A[2,2] = cos(θ).
        @test sol2(0.4, idxs = ya) ≈ cos(0.4) rtol = 1e-9
        @test sol2(0.4, idxs = w) ≈ 0.4 rtol = 1e-10
    end

    # -----------------------------------------------------------------------------------
    @testset "differentiability: jac = true on the D-MB6 pose path" begin
        R = SourceRange("", 1, 1, 1, 1)
        ast(x) = x isa Symbol ? Name(x, R) : Lit(x, R)
        vlit(xs) = VectorLit([ast(x) for x in xs], R)
        call(f, args) = Call(Name(f, R), args, R)

        # --- (a) the 7-chart pose state: dq = 0.5 q ⊗ [0, ω], dp = R(q) v ------------
        names = [Symbol("q$k") for k in 1:4]
        pnames = [Symbol("p$k") for k in 1:3]
        wnames = [Symbol("om$k") for k in 1:3]
        qv = [mtk_variable("mech.pose." * String(n)) for n in names]
        pv = [mtk_variable("mech.pose." * String(n)) for n in pnames]
        om = [mtk_variable("mech.pose." * String(n)) for n in wnames]
        ctx = LowerCtx(Dict{String,Num}(), Dict{String,Num}())
        for k in 1:4
            ctx.vars[String(names[k])] = qv[k]
        end
        for k in 1:3
            ctx.vars[String(pnames[k])] = pv[k]
            ctx.vars[String(wnames[k])] = om[k]
        end
        qlit = VectorLit([Name(n, R) for n in names], R)
        dp = lower_expression(call(:quat_compose, [qlit, vlit([0.0, :om1, :om2, :om3])]),
            ctx)
        dpv = lower_expression(call(:quat_rotate, [qlit, vlit([1.0, 0.0, 0.0])]), ctx)
        eqs = vcat([D(qv[k]) ~ 0.5 * dp[k] for k in 1:4],
            [D(pv[k]) ~ dpv[k] for k in 1:3])
        sys = mtkcompile(System(eqs, t, vcat(qv, pv), om; name = :mech_pose7))
        # A constant body rate about z: q(t) = (cos(ωt/2), 0, 0, sin(ωt/2)) from the
        # identity, and p(t) = (sin(ωt), 1 - cos(ωt), 0)/ω for R(q) (1, 0, 0).
        wr = 0.4
        op = [qv[1] => 1.0, qv[2] => 0.0, qv[3] => 0.0, qv[4] => 0.0,
            pv[1] => 0.0, pv[2] => 0.0, pv[3] => 0.0,
            om[1] => 0.0, om[2] => 0.0, om[3] => wr]
        # This is the case the reviewer proved fails with an opaque quaternion product.
        prob = ODEProblem(sys, op, (0.0, 0.5); jac = true)
        @test prob.f.jac !== nothing
        sol = solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        @test sol.retcode == ReturnCode.Success
        @test sol(0.5, idxs = qv[1]) ≈ cos(wr * 0.25) rtol = 1e-8
        @test sol(0.5, idxs = qv[2]) ≈ 0.0 atol = 1e-9
        @test sol(0.5, idxs = qv[3]) ≈ 0.0 atol = 1e-9
        @test sol(0.5, idxs = qv[4]) ≈ sin(wr * 0.25) rtol = 1e-8
        @test abs(sum(sol(0.5, idxs = qv[k])^2 for k in 1:4) - 1) < 1e-8
        @test sol(0.5, idxs = pv[1]) ≈ sin(0.5wr) / wr rtol = 1e-8
        @test sol(0.5, idxs = pv[2]) ≈ (1 - cos(0.5wr)) / wr rtol = 1e-8
        @test sol(0.5, idxs = pv[3]) ≈ 0.0 atol = 1e-9

        # --- (b) the symbolic Jacobian of the product and the rotation is the AD one ---
        qn = [mtk_variable("mech.jq$k") for k in 1:4]
        ctxj = LowerCtx(Dict{String,Num}("jq$k" => qn[k] for k in 1:4),
            Dict{String,Num}())
        qjlit = VectorLit([Name(Symbol("jq$k"), R) for k in 1:4], R)
        b = [0.0, 0.1, -0.2, 0.3]
        prod = lower_expression(call(:quat_compose, [qjlit, vlit(b)]), ctxj)
        rot = lower_expression(call(:quat_to_matrix, [qjlit]), ctxj)
        Jp = Symbolics.jacobian(prod, qn)          # 4x4
        Jr = Symbolics.jacobian(vec(rot), qn)      # 9x4
        hp = 1e-6
        qmul(q) = (qq = compose(Quat(q...), Quat(b...)); [qq.w, qq.x, qq.y, qq.z])
        qrot(q) = vec(collect(quat_to_matrix(Quat(q...))))
        E4 = Matrix{Float64}(I, 4, 4)
        # Several unit quaternions from the deterministic stream (a "random point").
        gq = _Stream(404)
        for _ in 1:8
            p0 = SVector(_sf(gq), _sf(gq), _sf(gq), _sf(gq))
            p0 = p0 / norm(p0)
            evalJ(x) = begin
                f = Symbolics.build_function(x, qn...; expression = Val(false))
                (f isa Tuple ? first(f) : f)(p0...)
            end
            # Central finite difference of the numeric core at the same point.
            fd(f) = reduce(hcat,
                [(f(collect(p0) + hp * e) .- f(collect(p0) - hp * e)) ./ (2hp)
                 for e in eachcol(E4)])
            Jpfd = fd(qmul)
            Jrfd = fd(qrot)
            @test maximum(abs, evalJ(Jp) - Jpfd) <= 1e-6 * max(1.0, maximum(abs, Jpfd))
            @test maximum(abs, evalJ(Jr) - Jrfd) <= 1e-6 * max(1.0, maximum(abs, Jrfd))
        end
        q0 = SVector(0.8, 0.1, -0.4, 0.3)
        q0 = q0 / norm(q0)

        # --- (c) an algebraic Ad(g(q)) with the quaternion components as states ----------
        gv = [mtk_variable("mech.adq$k") for k in 1:4]
        gp = [mtk_variable("mech.adp$k") for k in 1:3]
        ctxa = LowerCtx(Dict{String,Num}(), Dict{String,Num}())
        for k in 1:4
            ctxa.vars["adq$k"] = gv[k]
        end
        for k in 1:3
            ctxa.vars["adp$k"] = gp[k]
        end
        gchart = VectorLit(vcat([Name(Symbol("adq$k"), R) for k in 1:4],
            [Name(Symbol("adp$k"), R) for k in 1:3]), R)
        Ag = lower_expression(call(:Ad, [gchart]), ctxa)
        @test size(Ag) == (6, 6)
        @test !occursin("bg_quat", string(Ag))
        ya = mtk_variable("mech.ad_y")
        sysa = mtkcompile(System(
            vcat([D(gv[k]) ~ 0.0 for k in 1:4], [D(gp[k]) ~ 0.0 for k in 1:3],
                [ya ~ Ag[1, 1] + Ag[4, 5] + Ag[6, 3]]),
            t, vcat(gv, gp, [ya]), []; name = :mech_adstate,
        ))
        opa = vcat([gv[k] => q0[k] for k in 1:4], [gp[k] => 0.1 * k for k in 1:3])
        proba = ODEProblem(sysa, opa, (0.0, 0.1); jac = true)
        @test proba.f.jac !== nothing
        sola = solve(proba, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        @test sola.retcode == ReturnCode.Success
        Aref = Ad(SE3(quat_to_matrix(Quat(q0...)), SVector(0.1, 0.2, 0.3)))
        @test sola(0.0, idxs = ya) ≈ Aref[1, 1] + Aref[4, 5] + Aref[6, 3] rtol = 1e-9
        @test proba.f.jac !== nothing
    end
end
