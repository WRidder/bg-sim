# Spatial poses (SE(3)) as `(R, p)`: the pose of a body frame expressed in its base frame.
# Angular first, so a twist is `[ω; v]` and the adjoint is 6x6 (plan 3.1, D-MB2). The
# quaternion representation of the same pose (D-MB6) lives in `quat.jl`.

"""
    SE3{T}

A spatial pose: the rotation `R::SMatrix{3,3}` and the translation `p::SVector{3}` of the
body origin, expressed in the base frame. `SE3()` is the identity; `SE3(R, p)` validates
that `R` is a rotation (orthonormal within `1e-8`, `det = +1`) and throws otherwise;
`SE3(q, p)` builds it from a quaternion. The pose maps a body-frame point `x` to
`R * x + p`.
"""
struct SE3{T<:Real}
    R::SMatrix{3,3,T}
    p::SVector{3,T}
    # The one inner constructor suppresses the implicit `SE3(::SMatrix, ::SVector)`, so
    # the validating constructor below is the only way in from matrices.
    SE3{T}(R::SMatrix{3,3,T}, p::SVector{3,T}) where {T<:Real} = new{T}(R, p)
end

SE3() = _se3(SMatrix{3,3}(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    SVector(0.0, 0.0, 0.0))
SE3(q::Quat, p::AbstractVector) = SE3(quat_to_matrix(q), p)

function SE3(R::AbstractMatrix, p::AbstractVector; atol::Real = 1e-8)
    size(R) == (3, 3) || throw(ArgumentError("SE3 needs a 3x3 rotation, got $(size(R))"))
    length(p) == 3 || throw(ArgumentError(
        "SE3 needs a 3-vector position, got $(length(p)) components"
    ))
    M = SMatrix{3,3}(R)
    T = promote_type(eltype(M), eltype(p), Float64)
    Rb = SMatrix{3,3,T}(M)
    I3 = SMatrix{3,3,T}(one(T), zero(T), zero(T), zero(T), one(T), zero(T),
        zero(T), zero(T), one(T))
    dev = maximum(abs, Rb * transpose(Rb) - I3)
    if !(dev <= atol)
        throw(ArgumentError(
            "SE3: the rotation is not orthonormal; max |R Rᵀ - I| = $dev > $atol"
        ))
    end
    d = det(Rb)
    d > 0 || throw(ArgumentError(
        "SE3: the rotation has det(R) = $d <= 0; a pose needs det = +1"
    ))
    return _se3(Rb, SVector{3,T}(p))
end

# Unchecked constructor for the internal paths (`exp`, `log`, `compose`, `inv`), whose
# rotation products are orthonormal by construction.
function _se3(R::AbstractMatrix, p::AbstractVector)
    M = SMatrix{3,3}(R)
    T = promote_type(eltype(M), eltype(p), Float64)
    return SE3{T}(SMatrix{3,3,T}(M), SVector{3,T}(p))
end

"""    rotation(g::SE3) -> SMatrix{3,3}

The rotation block of a spatial pose."""
rotation(g::SE3) = g.R

"""
    chart(g::SE3) -> SVector{7}
    pose(::Type{SE3}, v) -> SE3

The language-level value of a spatial pose, `(q_w, q_x, q_y, q_z, p_x, p_y, p_z)`
(quaternion first, D-MB6), and its inverse. It is the `Vec{7}` shape the Symbolics-facing
functions in `src/lower/fnmap.jl` use; the quaternion is canonicalised to `q_w >= 0`, the
same branch [`quat_log`](@ref) takes.
"""
chart(g::SE3) = begin
    q = quat_from_rotation(g.R)
    SVector(q.w, q.x, q.y, q.z, g.p[1], g.p[2], g.p[3])
end
pose(::Type{SE3}, v::AbstractVector) =
    _se3(quat_to_matrix(Quat(v[1], v[2], v[3], v[4])), SVector{3}(v[5], v[6], v[7]))

"""    translation(g::SE3) -> SVector{3}

The translation part of a spatial pose: the body origin in base coordinates."""
translation(g::SE3) = g.p

"""
    compose(g1::SE3, g2::SE3) -> SE3
    g1 * g2

`g1 ∘ g2`: the pose of `g2`'s body expressed in `g1`'s base, `(R1 R2, p1 + R1 p2)`.
"""
compose(a::SE3, b::SE3) = _se3(a.R * b.R, a.p + a.R * b.p)
Base.:*(a::SE3, b::SE3) = compose(a, b)

"""
    inv(g::SE3) -> SE3

The inverse pose `(Rᵀ, -Rᵀp)`.
"""
inv(g::SE3) = _se3(transpose(g.R), -(transpose(g.R) * g.p))

"""
    Ad(g::SE3) -> SMatrix{6,6}

The spatial adjoint in the angular-first `[ω; v]` ordering,

    Ad(g) = [ R      0 ]
            [ p̂ R    R ]

which maps a twist expressed in the body frame to the base frame (plan 3.1, D-MB2). It is a
Lie-group homomorphism: `Ad(g1 * g2) == Ad(g1) * Ad(g2)`.
"""
function Ad(g::SE3{T}) where {T}
    R = g.R
    P = skew(g.p)
    PR = P * R
    Z = zero(R)
    return SMatrix{6,6,T}(
        R[1, 1], R[2, 1], R[3, 1], PR[1, 1], PR[2, 1], PR[3, 1],
        R[1, 2], R[2, 2], R[3, 2], PR[1, 2], PR[2, 2], PR[3, 2],
        R[1, 3], R[2, 3], R[3, 3], PR[1, 3], PR[2, 3], PR[3, 3],
        Z[1, 1], Z[2, 1], Z[3, 1], R[1, 1], R[2, 1], R[3, 1],
        Z[1, 2], Z[2, 2], Z[3, 2], R[1, 2], R[2, 2], R[3, 2],
        Z[1, 3], Z[2, 3], Z[3, 3], R[1, 3], R[2, 3], R[3, 3],
    )
end

# J_l(ω) = I + c1 ω̂ + c2 ω̂², c1 = (1-cos θ)/θ², c2 = (θ - sin θ)/θ³. The series below
# are used for θ < 1e-2 (error ~θ⁶/…, well under 1e-15 relative); at the switch the closed
# forms are accurate to ~1e-12 relative.
function _se3_c1(θ)
    if abs(θ) < 1e-2
        θ2 = θ^2
        return 0.5 - θ2 / 24 + θ2^2 / 720
    end
    return (1 - cos(θ)) / θ^2
end

function _se3_c2(θ)
    if abs(θ) < 1e-2
        θ2 = θ^2
        return 1 / 6 - θ2 / 120 + θ2^2 / 5040
    end
    return (θ - sin(θ)) / θ^3
end

# J_l(ω)⁻¹ = I - ½ ω̂ + c3 ω̂², c3 = (1 - (θ/2) cot(θ/2))/θ².
function _se3_c3(θ)
    if abs(θ) < 1e-2
        θ2 = θ^2
        return 1 / 12 + θ2 / 720 + θ2^2 / 30240
    end
    return (1 - (θ / 2) / tan(θ / 2)) / θ^2
end

"""
    exp(V::Twist{6}) -> SE3
    log(g::SE3) -> Twist{6}

The SE(3) exponential and logarithm (Rodrigues). `exp` uses `R = exp(ω̂)` and the left
Jacobian `p = J_l(ω) v`; `log` uses the quaternion branch of
[`quat_from_rotation`](@ref)/[`quat_log`](@ref) (so it stays accurate at and near a
rotation angle of π) and the inverse Jacobian
`v = p - ½ ω × p + c3 ω × (ω × p)`. `log` is the principal branch (`|ω| ≤ π`), and
`exp(log(g)) ≈ g` for every pose.

`exp(hat(V))` is the 4x4 homogeneous matrix of the same transform (see [`hat`](@ref)).
"""
function exp(V::Twist{6})
    ω = SVector{3}(V[1], V[2], V[3])
    v = SVector{3}(V[4], V[5], V[6])
    θ = sqrt(sum(abs2, ω))
    W = skew(ω)
    c1 = _se3_c1(θ)
    c2 = _se3_c2(θ)
    p = v + c1 * (W * v) + c2 * (W * (W * v))
    return _se3(quat_to_matrix(quat_exp(ω)), p)
end

function log(g::SE3)
    q = quat_from_rotation(g.R)
    ω = quat_log(q)
    θ = sqrt(sum(abs2, ω))
    W = skew(ω)
    c3 = _se3_c3(θ)
    p = g.p
    v = p - 0.5 * (W * p) + c3 * (W * (W * p))
    return Twist{6}(ω[1], ω[2], ω[3], v[1], v[2], v[3])
end
