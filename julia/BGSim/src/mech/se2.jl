# Planar poses (SE(2)) as `(θ, p)`: the pose of a body frame expressed in its base frame.
# Angular first, so the twist is `[ω, vx, vy]` and the adjoint is 3x3 (plan 3.1, D-MB2).

"""
    SE2{T}

A planar pose: the rotation `θ` (rad) followed by the translation `p::SVector{2}` (m) of
the body origin, expressed in the base frame. `SE2()` is the identity;
`SE2(θ, p)` and `SE2(θ, x, y)` construct one. The pose maps a body-frame point `q` to
`rotation(g) * q + translation(g)`.
"""
struct SE2{T<:Real}
    θ::T
    p::SVector{2,T}
    # The one inner constructor suppresses the implicit `SE2(::Real, ::SVector)`, so every
    # public construction goes through the promoting method below.
    SE2{T}(θ::T, p::SVector{2,T}) where {T<:Real} = new{T}(θ, p)
end

SE2() = SE2(0.0, SVector(0.0, 0.0))
SE2(θ::Real) = SE2(θ, SVector(0.0, 0.0))
SE2(θ::Real, x::Real, y::Real) = SE2(θ, SVector(x, y))

function SE2(θ::Real, p::AbstractVector)
    length(p) == 2 || throw(ArgumentError(
        "SE2 needs a 2-vector position, got $(length(p)) components"
    ))
    pv = SVector{2}(p)
    T = promote_type(typeof(θ), eltype(pv), Float64)
    return SE2{T}(T(θ), SVector{2,T}(pv))
end

"""    rotation(g::SE2) -> SMatrix{2,2}

The rotation block `[[cos θ, -sin θ], [sin θ, cos θ]]` of a planar pose."""
rotation(g::SE2) = SMatrix{2,2}(cos(g.θ), sin(g.θ), -sin(g.θ), cos(g.θ))

"""
    chart(g::SE2) -> SVector{3}
    pose(::Type{SE2}, v) -> SE2

The language-level value of a planar pose, `(θ, p_x, p_y)`, and its inverse. It is the
`Vec{3}` shape the Symbolics-facing functions in `src/lower/fnmap.jl` use, so a pose can
travel through a signal without a dedicated language type.
"""
chart(g::SE2) = SVector(g.θ, g.p[1], g.p[2])
pose(::Type{SE2}, v::AbstractVector) = SE2(v[1], SVector{2}(v[2], v[3]))

"""    translation(g::SE2) -> SVector{2}

The translation part of a planar pose: the body origin in base coordinates."""
translation(g::SE2) = g.p

"""
    compose(g1::SE2, g2::SE2) -> SE2
    g1 * g2

`g1 ∘ g2`: the pose of `g2`'s body expressed in `g1`'s base, i.e. `θ = θ1 + θ2`,
`p = p1 + R(θ1) p2`.
"""
compose(a::SE2, b::SE2) = SE2(a.θ + b.θ, a.p + rotation(a) * b.p)
Base.:*(a::SE2, b::SE2) = compose(a, b)

"""
    inv(g::SE2) -> SE2

The inverse pose `(Rᵀ, -Rᵀp)`.
"""
inv(g::SE2) = SE2(-g.θ, -(transpose(rotation(g)) * g.p))

"""
    Ad(g::SE2) -> SMatrix{3,3}

The planar adjoint in the `(ω, vx, vy)` ordering,

    [ 1    0    0  ]
    [ p_y  cosθ -sinθ ]
    [ -p_x sinθ  cosθ ]

which maps a twist expressed in the body frame to the base frame (plan 3.1). It is the
spatial `Ad` of the same pose restricted to the planar subalgebra: the **rows and columns
`(ω_z, v_x, v_y)`, i.e. indices 3, 4, 5** of the 6x6 `Ad` (the `ω_x`, `ω_y` and `v_z`
directions are dropped; dropping only the `z` row and column would not span SE(2)).
"""
function Ad(g::SE2{T}) where {T}
    c, s = cos(g.θ), sin(g.θ)
    # Columns: (1, p_y, -p_x), (0, c, s), (0, -s, c); i.e. rows [1 0 0; p_y c -s;
    # -p_x s c] as the adjoint of the (ω, vx, vy) ordering.
    return SMatrix{3,3,T}(one(T), g.p[2], -g.p[1],
        zero(T), c, s,
        zero(T), -s, c)
end

# sinc(θ) = sin θ / θ and c1(θ) = (1 - cos θ)/θ, with the small-angle series. The series
# is used below |θ| = 1e-2, where it is accurate to ~1e-18 and the closed forms still are
# not (1 - cos θ cancels); at the switch the closed form is good to ~1e-12 relative.
function _se2_sinc(θ)
    if abs(θ) < 1e-2
        θ2 = θ^2
        return one(θ) - θ2 / 6 + θ2^2 / 120 - θ2^3 / 5040
    end
    return sin(θ) / θ
end

function _se2_c1(θ)
    if abs(θ) < 1e-2
        θ2 = θ^2
        return θ / 2 - θ * θ2 / 24 + θ * θ2^2 / 720
    end
    return (1 - cos(θ)) / θ
end

"""
    exp(V::Twist{3}) -> SE2
    log(g::SE2) -> Twist{3}

The SE(2) exponential and logarithm with the small-angle branch `V(θ) = [[sinc θ,
-(1-cos θ)/θ], [(1-cos θ)/θ, sinc θ]]`. `log` takes the principal angle
`atan(sin θ, cos θ) ∈ (-π, π]`, so a pose with an angle near `2π` (the same rotation as one
near 0) round-trips exactly: `exp(log(g)) ≈ g`.

Note that `log` is only defined for poses, not for every twist: near a rotation of `2π` the
map `V(θ)` is singular, which is exactly why the angle is folded into the principal range
first.
"""
function exp(V::Twist{3})
    θ, vx, vy = V[1], V[2], V[3]
    s = _se2_sinc(θ)
    c = _se2_c1(θ)
    return SE2(θ, SVector(s * vx - c * vy, c * vx + s * vy))
end

function log(g::SE2{T}) where {T}
    θ = atan(sin(g.θ), cos(g.θ))  # principal value in (-π, π]
    a, b = _se2_log_coeffs(θ)
    vx = a * g.p[1] + b * g.p[2]
    vy = -b * g.p[1] + a * g.p[2]
    return Twist{3}(θ, vx, vy)
end

# a = (θ/2) cot(θ/2) = 1 - θ²/12 - θ⁴/720 - …, b = θ/2 (the inverse of `V(θ)`).
function _se2_log_coeffs(θ)
    if abs(θ) < 1e-2
        θ2 = θ^2
        return one(θ) - θ2 / 12 - θ2^2 / 720, θ / 2
    end
    return (θ / 2) / tan(θ / 2), θ / 2
end
