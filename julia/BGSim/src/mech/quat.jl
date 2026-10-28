# Unit quaternions as the pose state of a floating spatial body (D-MB6): `(w, x, y, z)`
# with the scalar part first, composing in the same order as `SE3` (`q1 ⊗ q2` is
# "`q2` relative to `q1`"). The rotation-vector exponential and logarithm are the ones
# `SE3`'s `exp`/`log` use, so a quaternion and a matrix pose never disagree on the branch.

"""
    Quat{T}

A quaternion `w + xi + yj + zk`, scalar part first. `Quat()` is the identity. Composition
(`compose(q1, q2)` or `q1 * q2`) follows the same order as [`SE3`](@ref) multiplication:
`q1 ⊗ q2` is the rotation of `q2` expressed through `q1`.
"""
struct Quat{T<:Real}
    w::T
    x::T
    y::T
    z::T
end

Quat() = Quat(1.0, 0.0, 0.0, 0.0)
Quat(w::Real, v::SVector{3}) = Quat(w, v[1], v[2], v[3])

function Quat(w::Real, v::AbstractVector)
    length(v) == 3 || throw(ArgumentError(
        "Quat(w, v) needs a 3-vector, got $(length(v)) components"
    ))
    return Quat(w, SVector{3}(v))
end

function Quat(v::AbstractVector)
    length(v) == 4 || throw(ArgumentError(
        "Quat(v) needs 4 components, got $(length(v))"
    ))
    return Quat(v[1], v[2], v[3], v[4])
end

Base.:+(a::Quat, b::Quat) = Quat(a.w + b.w, a.x + b.x, a.y + b.y, a.z + b.z)
Base.:-(a::Quat, b::Quat) = Quat(a.w - b.w, a.x - b.x, a.y - b.y, a.z - b.z)
Base.:-(a::Quat) = Quat(-a.w, -a.x, -a.y, -a.z)
Base.:*(α::Real, q::Quat) = Quat(α * q.w, α * q.x, α * q.y, α * q.z)
Base.:*(q::Quat, α::Real) = α * q
Base.:/(q::Quat, α::Real) = Quat(q.w / α, q.x / α, q.y / α, q.z / α)

"""    quat_norm(q) -> Real

The Euclidean norm `sqrt(w² + x² + y² + z²)`; `1` for a unit quaternion."""
quat_norm(q::Quat) = sqrt(q.w^2 + q.x^2 + q.y^2 + q.z^2)

"""
    compose(q1::Quat, q2::Quat) -> Quat
    q1 * q2

Hamilton product: the rotation `q1` followed by the rotation `q2` relative to it, matching
[`compose`](@ref) of poses. The product is not renormalised or sign-canonicalised (a product
of two unit quaternions is unit to rounding; `q` and `-q` are the same rotation), which is
what the D-MB6 state path wants — the integrator's manifold projection keeps the norm.
"""
compose(a::Quat, b::Quat) = Quat(
    a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
)
Base.:*(a::Quat, b::Quat) = compose(a, b)

"""
    inv(q::Quat) -> Quat

The multiplicative inverse `conj(q) / |q|²`; the conjugate for a unit quaternion. Throws
for the zero quaternion.
"""
function inv(q::Quat{T}) where {T}
    n2 = q.w^2 + q.x^2 + q.y^2 + q.z^2
    n2 > 0 || throw(ArgumentError("inv: the zero quaternion has no inverse"))
    return Quat(q.w / n2, -q.x / n2, -q.y / n2, -q.z / n2)
end

"""
    normalise(q::Quat) -> Quat

`q / |q|`. Throws for the zero quaternion: a zero state is a modelling error, not a pose.
"""
function normalise(q::Quat{T}) where {T}
    n = quat_norm(q)
    n > 0 || throw(ArgumentError("normalise: the zero quaternion is not a rotation"))
    return Quat(q.w / n, q.x / n, q.y / n, q.z / n)
end

"""
    quat_to_matrix(q) -> SMatrix{3,3}
    rotation(q::Quat) -> SMatrix{3,3}

The rotation matrix of `normalise(q)`, i.e. the active rotation `v -> q v q*`.
"""
function quat_to_matrix(q::Quat)
    u = normalise(q)
    w, x, y, z = u.w, u.x, u.y, u.z
    return SMatrix{3,3}(
        1 - 2 * (y^2 + z^2), 2 * (x * y + w * z), 2 * (x * z - w * y),
        2 * (x * y - w * z), 1 - 2 * (x^2 + z^2), 2 * (y * z + w * x),
        2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x^2 + y^2),
    )
end
rotation(q::Quat) = quat_to_matrix(q)

"""
    quat_from_rotation(R) -> Quat

The unit quaternion of a rotation matrix, using Shepperd's branch on the largest of the
trace and the three diagonal entries, so it stays accurate at and near a rotation angle of
π. The result is **canonicalised to `q_w >= 0`** (the same branch [`quat_log`](@ref) and
`chart` use); a quaternion and its negative are the same rotation, so this fixes the sign
of a conversion but does not change the rotation. Throws when `R` is not a rotation
(non-orthonormal within `1e-6`, or `det(R) <= 0`).
"""
function quat_from_rotation(R::AbstractMatrix)
    size(R) == (3, 3) || throw(ArgumentError("quat_from_rotation: expected a 3x3 matrix"))
    M = SMatrix{3,3}(R)
    if !isapprox(M * transpose(M), SMatrix{3,3}(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0);
        atol = 1e-6, rtol = 0)
        throw(ArgumentError("quat_from_rotation: the matrix is not orthonormal"))
    end
    d = M[1, 1] * (M[2, 2] * M[3, 3] - M[2, 3] * M[3, 2]) -
        M[1, 2] * (M[2, 1] * M[3, 3] - M[2, 3] * M[3, 1]) +
        M[1, 3] * (M[2, 1] * M[3, 2] - M[2, 2] * M[3, 1])
    d > 0 || throw(ArgumentError(
        "quat_from_rotation: det(R) = $d <= 0; a rotation matrix needs det = +1"
    ))
    tr = M[1, 1] + M[2, 2] + M[3, 3]
    if tr > 0
        s = 2 * sqrt(tr + 1)
        q = Quat(0.25 * s, (M[3, 2] - M[2, 3]) / s, (M[1, 3] - M[3, 1]) / s,
            (M[2, 1] - M[1, 2]) / s)
    elseif M[1, 1] > M[2, 2] && M[1, 1] > M[3, 3]
        s = 2 * sqrt(1 + M[1, 1] - M[2, 2] - M[3, 3])
        q = Quat((M[3, 2] - M[2, 3]) / s, 0.25 * s, (M[1, 2] + M[2, 1]) / s,
            (M[1, 3] + M[3, 1]) / s)
    elseif M[2, 2] > M[3, 3]
        s = 2 * sqrt(1 + M[2, 2] - M[1, 1] - M[3, 3])
        q = Quat((M[1, 3] - M[3, 1]) / s, (M[1, 2] + M[2, 1]) / s, 0.25 * s,
            (M[2, 3] + M[3, 2]) / s)
    else
        s = 2 * sqrt(1 + M[3, 3] - M[1, 1] - M[2, 2])
        q = Quat((M[2, 1] - M[1, 2]) / s, (M[1, 3] + M[3, 1]) / s,
            (M[2, 3] + M[3, 2]) / s, 0.25 * s)
    end
    return _canonical(normalise(q))
end

# The canonical branch of the quaternion of a rotation: `q` and `-q` are the same
# rotation, and `q_w >= 0` is the branch `quat_log` and `chart` take, so a pose chart never
# jumps sign when the angle passes π. Only the *conversion* paths canonicalise:
# `quat_from_rotation`, `chart` and `quat_log`. The algebra (`compose`, `inv`,
# `normalise`, `quat_exp`, `quat_to_matrix`) does **not** canonicalise — a product of two
# canonical quaternions can have `q_w < 0`, and that is still the same rotation.
function _canonical(q::Quat)
    return q.w < 0 ? -q : q
end

"""
    quat_rotate(q, v) -> SVector{3}

Rotate a 3-vector by `normalise(q)`, `v' = q v q*`. Same result as `quat_to_matrix(q) * v`,
without forming the matrix.
"""
function quat_rotate(q::Quat, v::AbstractVector)
    u = normalise(q)
    p = Quat(0.0, SVector{3}(v))
    r = u * p * inv(u)
    return SVector{3}(r.x, r.y, r.z)
end

"""
    quat_exp(v::SVector{3}) -> Quat

The exponential of the rotation vector `v` (axis times angle): `(cos(θ/2),
sin(θ/2) v̂)` with `θ = |v|`. Small-angle branch through `sin(θ/2)/θ`. The result is unit
norm but **not** canonicalised (a rotation of more than π gives `q_w < 0`; both signs are
the same rotation).
"""
function quat_exp(v::SVector{3,T}) where {T}
    θ = sqrt(v[1]^2 + v[2]^2 + v[3]^2)
    half = θ / 2
    s = abs(half) < 1e-8 ? (one(half) - half^2 / 6 + half^4 / 120) : sin(half) / half
    return Quat(cos(half), s * v[1] / 2, s * v[2] / 2, s * v[3] / 2)
end
quat_exp(v::AbstractVector) = quat_exp(SVector{3}(v))

"""
    quat_log(q) -> SVector{3}

The principal rotation vector of `q`: `θ û` with `θ = 2 atan(|q_v|, q_w) ∈ [0, π]` after
canonicalising the sign of `q`, so `quat_exp(quat_log(q))` is `±q` with a rotation angle in
`[0, π]`. Small-angle branch `2 q_v / q_w`. This is a *conversion*, so it does canonicalise;
the algebra (`compose`, `inv`) does not.
"""
function quat_log(q::Quat{T}) where {T}
    u = normalise(q)
    # A quaternion and its negative are the same rotation; take the branch with w >= 0.
    u = u.w < 0 ? -u : u
    nv = sqrt(u.x^2 + u.y^2 + u.z^2)
    if nv < 1e-12
        s = nv == 0 ? zero(T) : 2 / u.w
        return SVector{3}(s * u.x, s * u.y, s * u.z)
    end
    s = 2 * atan(nv, u.w) / nv
    return SVector{3}(s * u.x, s * u.y, s * u.z)
end
quat_log(v::AbstractVector) = quat_log(Quat(v))

"""
    exp(q::Quat) -> Quat
    log(q::Quat) -> Quat

The quaternion exponential and logarithm (scalar part first). `exp` maps
`w + v` to `e^w (cos|v| + sin|v| v̂)`; `log` inverts it for the principal branch. The pose
code uses the vector forms [`quat_exp`](@ref) and [`quat_log`](@ref); these general ones are
what they are built on.
"""
function exp(q::Quat{T}) where {T}
    n = sqrt(q.x^2 + q.y^2 + q.z^2)
    e = exp(q.w)
    s = n < 1e-8 ? e * (one(n) - n^2 / 6) : e * sin(n) / n
    return Quat(e * cos(n), s * q.x, s * q.y, s * q.z)
end

function log(q::Quat{T}) where {T}
    n = quat_norm(q)
    n > 0 || throw(ArgumentError("log: the zero quaternion has no logarithm"))
    u = q / n
    nv = sqrt(u.x^2 + u.y^2 + u.z^2)
    s = if nv < 1e-12
        u.w == 0 ? zero(T) : 1 / u.w
    else
        atan(nv, u.w) / nv
    end
    return Quat(log(n), s * u.x, s * u.y, s * u.z)
end
