# Screws, the adjoint actions and spatial inertia: the dimension-generic part of the Lie
# core (`D = 3` planar, `D = 6` spatial, angular first everywhere).
#
# Conventions (frozen; see NOTES.md "J-MB3 - Lie core"):
#
# * a twist is the flow `[ω; v]` and a wrench the effort `[m; f]`, both as
#   `SVector{D}`-backed `Twist{D}` / `Wrench{D}` values;
# * the linear part of a twist is the velocity of the **frame origin**, not of the centre of
#   mass and not of a joint point (plan 3.1, last bullet: the planar revolute screw
#   `[1, r_y, -r_x]` is the origin-velocity convention);
# * `Ad(g)` changes the frame of a twist, `Ad(inv(g))'` changes the frame of a wrench, and
#   `ad(V)` is the Lie bracket used by the Euler/Coriolis term;
# * an inertia is expressed about the **body origin**; `spatial_inertia` takes the rotational
#   inertia about the centre of mass and the CoM offset, both in body coordinates.

"""
    Screw{D,T} <: AbstractVector{T}

The shared supertype of [`Twist`](@ref) and [`Wrench`](@ref): a `D`-component screw
(`D = 3` planar, `D = 6` spatial) that behaves like an `SVector` (indexing, `+`, `-`,
scalar scaling, `norm`, `dot`, `isapprox`) while keeping twists and wrenches apart in
dispatch.
"""
abstract type Screw{D,T<:Real} <: AbstractVector{T} end

"""
    Twist{D,T}

A twist (flow) in angular-first order: `[ω; v]`. `D = 3` is the planar
`(ω, vx, vy)`; `D = 6` the spatial `(ωx, ωy, ωz, vx, vy, vz)`. The linear part is the
velocity of the **frame origin** expressed in that frame.
"""
struct Twist{D,T<:Real} <: Screw{D,T}
    v::SVector{D,T}
end

"""
    Wrench{D,T}

A wrench (effort) in angular-first order: `[m; f]`. `D = 3` is the planar
`(τ, fx, fy)`; `D = 6` the spatial `(mx, my, mz, fx, fy, fz)`, expressed in one frame.
"""
struct Wrench{D,T<:Real} <: Screw{D,T}
    v::SVector{D,T}
end

# ---------------------------------------------------------------------------------------
# Construction and the AbstractVector interface
# ---------------------------------------------------------------------------------------

for S in (:Twist, :Wrench)
    @eval begin
        $S{D}(xs::Vararg{Real,D}) where {D} = $S{D}(promote(xs...))
        $S{D}(xs::Tuple{Vararg{Real,D}}) where {D} = begin
            p = promote(xs...)
            $S{D,typeof(p[1])}(SVector{D,typeof(p[1])}(p))
        end
        $S{D}(v::AbstractVector) where {D} = begin
            length(v) == D || throw(ArgumentError(
                "$($S){$D} needs $D components, got $(length(v))"
            ))
            $S{D}(promote(Tuple(v)...))
        end
        $S(v::AbstractVector) = $S{length(v)}(v)
        Base.zero(::$S{D,T}) where {D,T} = $S{D,T}(zero(SVector{D,T}))
    end
end

# The AbstractVector interface and the arithmetic are shared by both screw types (the type
# parameter `S` keeps a twist and a wrench apart).
Base.size(::Screw{D}) where {D} = (D,)
Base.getindex(s::Screw, i::Int) = s.v[i]
Base.IndexStyle(::Type{<:Screw}) = IndexLinear()
Base.parent(s::Screw) = s.v
StaticArrays.SVector{D}(s::Screw{D}) where {D} = s.v
StaticArrays.SVector(s::Screw{D}) where {D} = s.v

Base.:+(a::S, b::S) where {S<:Screw} = S(a.v + b.v)
Base.:-(a::S, b::S) where {S<:Screw} = S(a.v - b.v)
# Base's elementwise `+(::AbstractArray, ::AbstractArray)` would silently mix them.
Base.:+(a::Twist, b::Wrench) = throw(ArgumentError(
    "a twist and a wrench cannot be added: they are different types of screw"
))
Base.:+(a::Wrench, b::Twist) = throw(ArgumentError(
    "a twist and a wrench cannot be added: they are different types of screw"
))
Base.:-(a::Twist, b::Wrench) = throw(ArgumentError(
    "a twist and a wrench cannot be subtracted: they are different types of screw"
))
Base.:-(a::Wrench, b::Twist) = throw(ArgumentError(
    "a twist and a wrench cannot be subtracted: they are different types of screw"
))
Base.:-(a::S) where {S<:Screw} = S(-a.v)
Base.:*(α::Number, a::S) where {S<:Screw} = S(α * a.v)
Base.:*(a::S, α::Number) where {S<:Screw} = S(a.v * α)

# Matrix products with the matrix types the pose algebra produces: a dense `Matrix`, a
# `StaticMatrix`, a `Diagonal`, and their transposes/adjoints. Deliberately **not** every
# `AbstractMatrix` and not a `Union`, so each method is more specific than LinearAlgebra's and
# StaticArrays' `AbstractVector` products (checked with `Test.detect_ambiguities`).
#
# Only **twists** are accepted. A wrench is the dual of a twist: it transforms with
# `Ad(inv(g))'`, so `Ad(g) * W` would return a plausible but wrong value. Every matrix x
# wrench product therefore throws with a hint, and [`AdDual`](@ref) is the typo-proof way to
# change a wrench's frame.
const _WRENCH_MUL_HINT =
    "a wrench transforms with the dual of a matrix, not with the matrix itself: use " *
    "`AdDual(g) * W` (a pose, `W = Ad(inv(g))' W`), or `Wrench(transpose(M) * W.v)` for a " *
    "matrix you assembled yourself (for example `transpose(ad(V))`)"

_wrench_mul_error() = throw(ArgumentError(_WRENCH_MUL_HINT))

for M in (:(StaticArrays.StaticMatrix), :(Matrix), :(Diagonal))
    @eval Base.:*(A::$M, a::S) where {S<:Twist} = S(SVector{size(A, 1)}(A * a.v))
    @eval Base.:*(A::Transpose{<:Any,<:$M}, a::S) where {S<:Twist} =
        S(SVector{size(A, 1)}(A * a.v))
    @eval Base.:*(A::Adjoint{<:Any,<:$M}, a::S) where {S<:Twist} =
        S(SVector{size(A, 1)}(A * a.v))
    @eval Base.:*(A::$M, w::Wrench) = _wrench_mul_error()
    @eval Base.:*(A::Transpose{<:Any,<:$M}, w::Wrench) = _wrench_mul_error()
    @eval Base.:*(A::Adjoint{<:Any,<:$M}, w::Wrench) = _wrench_mul_error()
end

"""
    AdDual(g) -> CoAdjoint

The **wrench** transform of a pose `g`: `AdDual(g) * W` maps a wrench from the body frame to
the base frame, `W_base = Ad(inv(g))' W_body`, which keeps `dot(W, V)` frame invariant. It is
a small wrapper rather than a bare matrix because `Ad(g) * W` (the twist rule applied to a
wrench) is a common and silent error: that expression throws an `ArgumentError`.

A `CoAdjoint` only multiplies a [`Wrench`](@ref); `AdDual(g) * V` for a twist is a
`MethodError` (use `Ad(g) * V`).
"""
struct CoAdjoint{P,M}
    pose::P
    M::M
end

AdDual(g) = CoAdjoint(g, transpose(Ad(inv(g))))
AdDual(g::CoAdjoint) = g

Base.:*(A::CoAdjoint, w::Wrench{D}) where {D} = Wrench{D}(SVector{D}(A.M * w.v))
Base.Matrix(A::CoAdjoint) = Matrix(A.M)
Base.size(A::CoAdjoint) = size(A.M)
Base.getindex(A::CoAdjoint, i::Int, j::Int) = A.M[i, j]

# ---------------------------------------------------------------------------------------
# hat / vee
# ---------------------------------------------------------------------------------------

"""
    skew(v::SVector{3}) -> SMatrix{3,3}

The cross-product matrix of a 3-vector: `skew(v) * w == cross(v, w)`.
"""
function skew(v::SVector{3,T}) where {T}
    z = zero(T)
    return SMatrix{3,3,T}(z, v[3], -v[2], -v[3], z, v[1], v[2], -v[1], z)
end
skew(v::AbstractVector) = skew(SVector{3}(v))

"""
    hat(V::Twist{3}) -> SMatrix{3,3}

The `se(2)` matrix of a planar twist `[ω, vx, vy]`:

    [ 0  -ω  vx ]
    [ ω   0  vy ]
    [ 0   0   0 ]

`exp(hat(V))` is the homogeneous transform of [`exp(V)`](@ref).
"""
function hat(V::Twist{3,T}) where {T}
    ω, vx, vy = V[1], V[2], V[3]
    z = zero(T)
    return SMatrix{3,3,T}(z, ω, z, -ω, z, z, vx, vy, z)
end

"""
    hat(V::Twist{6}) -> SMatrix{4,4}

The `se(3)` matrix of a spatial twist `[ω; v]`, `[[ω̂, v], [0, 0]]`, i.e. the homogeneous
transform `exp(hat(V))` of [`exp(V)`](@ref).
"""
function hat(V::Twist{6,T}) where {T}
    W = skew(SVector{3,T}(V[1], V[2], V[3]))
    v = SVector{3,T}(V[4], V[5], V[6])
    z = zero(T)
    return SMatrix{4,4,T}(
        W[1, 1], W[2, 1], W[3, 1], z,
        W[1, 2], W[2, 2], W[3, 2], z,
        W[1, 3], W[2, 3], W[3, 3], z,
        v[1], v[2], v[3], z,
    )
end

"""
    vee(M::AbstractMatrix) -> Twist{3} / Twist{6}

The inverse of [`hat`](@ref): the twist whose `hat` matrix is `M`. A 3x3 matrix is read as
an `se(2)` element, a 4x4 matrix as an `se(3)` element.
"""
vee(M::SMatrix{3,3,T}) where {T} = Twist{3,T}(SVector{3,T}(M[2, 1], M[1, 3], M[2, 3]))
vee(M::SMatrix{4,4,T}) where {T} = Twist{6,T}(
    SVector{6,T}(M[3, 2], M[1, 3], M[2, 1], M[1, 4], M[2, 4], M[3, 4])
)
vee(M::AbstractMatrix) = vee(SMatrix{size(M, 1),size(M, 2)}(M))

# ---------------------------------------------------------------------------------------
# ad
# ---------------------------------------------------------------------------------------

"""
    ad(V::Twist{3}) -> SMatrix{3,3}

The planar Lie bracket matrix of a twist, `ad(V) = [[0,0,0], [vy,0,-ω], [-vx,ω,0]]` in the
`(ω, vx, vy)` ordering (plan 3.1). It is the restriction of the spatial `ad` to the plane,
satisfies `ad(V) * V == 0`, and its transpose is the gyrator of the Coriolis element
(`dot(V, ad(V)' * P) == 0`).
"""
function ad(V::Twist{3,T}) where {T}
    ω, vx, vy = V[1], V[2], V[3]
    z = zero(T)
    return SMatrix{3,3,T}(z, vy, -vx, z, z, ω, z, -ω, z)
end

"""
    ad(V::Twist{6}) -> SMatrix{6,6}

The spatial Lie bracket matrix `[[ω̂, 0], [v̂, ω̂]]` of a twist `[ω; v]` (plan 3.1), in the
angular-first ordering. `ad(V) * V == 0`.
"""
function ad(V::Twist{6,T}) where {T}
    W = skew(SVector{3,T}(V[1], V[2], V[3]))
    Vc = skew(SVector{3,T}(V[4], V[5], V[6]))
    Z = zero(W)
    return SMatrix{6,6,T}(
        W[1, 1], W[2, 1], W[3, 1], Vc[1, 1], Vc[2, 1], Vc[3, 1],
        W[1, 2], W[2, 2], W[3, 2], Vc[1, 2], Vc[2, 2], Vc[3, 2],
        W[1, 3], W[2, 3], W[3, 3], Vc[1, 3], Vc[2, 3], Vc[3, 3],
        Z[1, 1], Z[2, 1], Z[3, 1], W[1, 1], W[2, 1], W[3, 1],
        Z[1, 2], Z[2, 2], Z[3, 2], W[1, 2], W[2, 2], W[3, 2],
        Z[1, 3], Z[2, 3], Z[3, 3], W[1, 3], W[2, 3], W[3, 3],
    )
end

"""
    Ad(g) -> SMatrix{D,D}

The adjoint of a pose: the matrix that maps a twist expressed in the pose's body frame to
the same twist expressed in its base frame (`V_base = Ad(g) * V_body`).

A wrench is the **dual** of a twist and does **not** transform with `Ad(g)`: it transforms
with the inverse transpose, `W_base = Ad(inv(g))' * W_body`, so that `dot(W, V)` is frame
invariant. Use [`AdDual`](@ref) for that (`AdDual(g) * W`); `Ad(g) * W` throws, because it
looks plausible and is wrong. Defined per pose type in `se2.jl` and `se3.jl`.
"""
function Ad end

"""
    compose(g1, g2) -> Pose

Pose composition `g1 ∘ g2` ("`g2` relative to `g1`"), also written `g1 * g2`. Defined per
pose type in `se2.jl`, `se3.jl` and `quat.jl`.
"""
function compose end

"""
    rotation(g) -> SMatrix

The rotation block of a pose (or of a quaternion).
"""
function rotation end

"""
    translation(g) -> SVector

The translation part of a pose.
"""
function translation end

# ---------------------------------------------------------------------------------------
# Joint screws
# ---------------------------------------------------------------------------------------

"""
    screw(axis, point, pitch = 0) -> Twist{6}

The twist of a helical joint: unit `axis`, a `point` on the axis, and the `pitch`
(metres of translation per radian, `0` for a revolute joint). The linear part is the
**origin velocity** (plan 3.1): `v = cross(point, axis) + pitch * axis`, so for a pure
rotation about `axis` through `point` the velocity at the origin is `ω × (0 - point)`.

The axis is normalised (the screw is the unit-ω twist) and a zero axis is refused.
"""
function screw(axis::SVector{3}, point::SVector{3}, pitch::Real = 0)
    n = norm(axis)
    n > 0 || throw(ArgumentError("screw: the axis must be a non-zero vector"))
    a = axis / n
    return Twist{6}(a[1], a[2], a[3],
        (point[2] * a[3] - point[3] * a[2]) + pitch * a[1],
        (point[3] * a[1] - point[1] * a[3]) + pitch * a[2],
        (point[1] * a[2] - point[2] * a[1]) + pitch * a[3])
end

"""
    revolute_screw(axis, point) -> Twist
    revolute_screw(point::SVector{2}) -> Twist{3}

The twist of a revolute joint about `axis` through `point`, both in one frame. The axis is
normalised. The planar form takes only the point and returns the plan 3.1 screw
`[1, r_y, -r_x]` — the **unit-ω** convention, so the joint coordinate is the angle in
radians and the origin velocity is `ω × (0 - r)`.
"""
revolute_screw(axis::SVector{3}, point::SVector{3}) = screw(axis, point, 0)
revolute_screw(axis::AbstractVector, point::AbstractVector) =
    revolute_screw(SVector{3}(axis), SVector{3}(point))
revolute_screw(point::SVector{2}) = Twist{3}(1.0, point[2], -point[1])

"""
    prismatic_screw(axis) -> Twist

The twist of a prismatic joint along `axis`: `[0; axis]` with the axis **normalised**, so
the joint coordinate is the displacement in metres (`f = ẋ`). A zero axis is refused rather
than silently producing a zero twist.
"""
function prismatic_screw(axis::SVector{3})
    n = norm(axis)
    n > 0 || throw(ArgumentError("prismatic_screw: the axis must be a non-zero vector"))
    a = axis / n
    return Twist{6}(0.0, 0.0, 0.0, a[1], a[2], a[3])
end

function prismatic_screw(axis::SVector{2})
    n = norm(axis)
    n > 0 || throw(ArgumentError("prismatic_screw: the axis must be a non-zero vector"))
    a = axis / n
    return Twist{3}(0.0, a[1], a[2])
end

prismatic_screw(axis::AbstractVector) =
    length(axis) == 2 ? prismatic_screw(SVector{2}(axis)) :
    prismatic_screw(SVector{3}(axis))

"""
    joint_basis(Vs) -> SMatrix{D,N}

The `D x N` joint basis `S` whose columns are the joint screws `Vs` (D-MB8: one scalar
power port per axis, `S` as a `Mat{D,N}` transformer). Column `n` is `Vs[n]`.
"""
function joint_basis(Vs::AbstractVector{<:Twist{D}}) where {D}
    N = length(Vs)
    N == 0 && throw(ArgumentError("joint_basis: at least one screw is needed"))
    return SMatrix{D,N}(reduce(hcat, [SVector{D}(v) for v in Vs]))
end
joint_basis(Vs::Vararg{Twist{D}}) where {D} = joint_basis(collect(Vs))

# ---------------------------------------------------------------------------------------
# Spatial inertia
# ---------------------------------------------------------------------------------------

const INERTIA_RTOL = 1e-12

"""
    validate_inertia(M; atol = 0, rtol = 1e-12) -> M

Check that `M` is a symmetric positive definite spatial inertia (6x6) or planar inertia
(3x3) and return it. `rtol` is the one symmetry tolerance used everywhere a physical inertia
is checked (here and for the rotational block in [`spatial_inertia`](@ref)), so a matrix
that is symmetric to rounding is accepted by both and a real asymmetry is rejected by both.
Throws an `ArgumentError` naming the failed property when it is not: a silently accepted
non-SPD inertia makes a body with negative mass simulate happily and lie about its energy
(the E108 case of plan C-MB1).
"""
function validate_inertia(M::AbstractMatrix; atol::Real = 0, rtol::Real = INERTIA_RTOL)
    n = size(M, 1)
    (n == 6 || n == 3) && size(M, 2) == n ||
        throw(ArgumentError("inertia: expected a 3x3 or 6x6 matrix, got $(size(M))"))
    if !isapprox(M, transpose(M); atol = atol, rtol = rtol)
        throw(ArgumentError(
            "inertia: the matrix is not symmetric; a spatial inertia must equal its " *
            "transpose (largest mismatch $(maximum(abs, M - transpose(M))) > " *
            "rtol $(rtol) of $(maximum(abs, M)))"
        ))
    end
    S = Symmetric(SMatrix{n,n}(Float64.(M)))
    if !isposdef(S)
        throw(ArgumentError(
            "inertia: the matrix is not positive definite, so the body would have a " *
            "non-positive mass or a non-physical inertia tensor: $M"
        ))
    end
    return M
end

"""
    planar_inertia(m, J, c = SVector(0, 0)) -> SMatrix{3,3}

The planar spatial inertia for the `(ω, vx, vy)` ordering with the body frame at its
origin, mass `m`, rotational inertia `J` about the centre of mass and the centre of mass
at `c` (body coordinates):

    [ J + m|c|^2   -m c_y   m c_x ]
    [   -m c_y        m       0   ]
    [    m c_x        0       m   ]

It is the plane restriction of [`spatial_inertia`](@ref)'s `[[Jc + m ĉ ĉᵀ, m ĉ],
[m ĉᵀ, m I]]`, so at `c = 0` it is the D-MB3 v1 `diag(J, m, m)` case. Throws when `m <= 0`,
`J <= 0` or the result is not positive definite.
"""
function planar_inertia(m::Real, J::Real, c::SVector{2} = SVector(0.0, 0.0))
    m > 0 || throw(ArgumentError("planar_inertia: the mass must be positive, got m = $m"))
    J > 0 || throw(ArgumentError(
        "planar_inertia: the rotational inertia must be positive, got J = $J"
    ))
    M = SMatrix{3,3}(J + m * (c[1]^2 + c[2]^2), -m * c[2], m * c[1],
        -m * c[2], m, zero(m), m * c[1], zero(m), m)
    return validate_inertia(M)
end
planar_inertia(m::Real, J::Real, cx::Real, cy::Real) = planar_inertia(m, J, SVector(cx, cy))

# The entry-wise builders shared with the Symbolics-facing `bg_*` functions of
# `src/lower/fnmap.jl`: they perform no validation (the parameters are validated once at
# model build by `spatial_inertia`), so they stay allocation-free and generic over the AD
# duals the solver's Jacobian passes in.
function _inertia_entry(m, Ic::AbstractMatrix, c::SVector{3}, i::Int, j::Int)
    if i <= 3 && j <= 3
        # (Jc + m ĉ ĉᵀ)[i, j] with ĉ ĉᵀ = |c|² I - c cᵀ
        return Ic[i, j] + m * ((i == j ? sum(abs2, c) : zero(m)) - c[i] * c[j])
    elseif i <= 3
        return m * skew(c)[i, j - 3]
    elseif j <= 3
        return m * skew(c)[j, i - 3]
    else
        return i == j ? m : zero(m)
    end
end

"""
    inertia_entry(m, J::SVector{3}, c::SVector{3}, i, j) -> Real

The `(i, j)` entry of `spatial_inertia(m, J, c)` (the diagonal `Ic = diag(J)` case of
D-MB3) without building or validating the matrix. The Symbolics-facing `bg_inertia3` in
`src/lower/fnmap.jl` calls this per component, so a native block can write the inertia
component-wise (D-MB10) and the solver's Jacobian can differentiate it with duals.
"""
function inertia_entry(m, J::SVector{3}, c::SVector{3}, i::Int, j::Int)
    z = zero(m)
    if i <= 3 && j <= 3
        return (i == j ? J[i] : z) + m * ((i == j ? sum(abs2, c) : z) - c[i] * c[j])
    elseif i <= 3
        return m * skew(c)[i, j - 3]
    elseif j <= 3
        return m * skew(c)[j, i - 3]
    else
        return i == j ? m : z
    end
end

"""
    spatial_inertia(m, Ic, c = zeros(3)) -> SMatrix{6,6}
    spatial_inertia(m, J::SVector{3}, c = zeros(3)) -> SMatrix{6,6}

The 6x6 spatial inertia about the **body origin** in the angular-first `[ω; v]` ordering
(plan 3.1):

    M = [ Jc + m ĉ ĉᵀ   m ĉ ]
        [   m ĉᵀ        m I ]

with `Ic` the rotational inertia about the centre of mass and `c` the CoM offset, both in
body coordinates. The `SVector{3}` form takes the principal moments `diag(J)` and is the
D-MB3 v1 body (`J::Vec{3}`, `m::Real`); with `c = 0` it reduces to `diag(J, m I)`.

Throws an `ArgumentError` (never accepts silently) when `m <= 0`, `Ic` is not symmetric
positive definite, or the composed matrix is not SPD — the E108 case.
"""
function spatial_inertia(m::Real, Ic::AbstractMatrix, c::AbstractVector = SVector(0.0, 0.0, 0.0))
    m > 0 || throw(ArgumentError("spatial_inertia: the mass must be positive, got m = $m"))
    size(Ic) == (3, 3) || throw(ArgumentError(
        "spatial_inertia: the rotational inertia must be 3x3, got $(size(Ic))"
    ))
    Ic32 = SMatrix{3,3}(Float64.(Ic))
    if !isapprox(Ic32, transpose(Ic32); atol = 0, rtol = INERTIA_RTOL)
        throw(ArgumentError("spatial_inertia: the rotational inertia is not symmetric: $Ic"))
    end
    if !isposdef(Symmetric(Ic32))
        throw(ArgumentError(
            "spatial_inertia: the rotational inertia is not positive definite: $Ic"
        ))
    end
    cv = SVector{3}(c)
    M = SMatrix{6,6}([_inertia_entry(m, Ic32, cv, i, j) for i in 1:6, j in 1:6])
    return validate_inertia(M)
end
spatial_inertia(m::Real, J::SVector{3}, c::SVector{3} = SVector(0.0, 0.0, 0.0)) =
    spatial_inertia(m, SMatrix{3,3}(J[1], zero(J[1]), zero(J[1]),
        zero(J[2]), J[2], zero(J[2]), zero(J[3]), zero(J[3]), J[3]), c)
spatial_inertia(m::Real, J::SVector{3}, c::AbstractVector) = spatial_inertia(m, J, SVector{3}(c))
