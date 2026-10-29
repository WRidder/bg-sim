# Impact (impulse) projection of a rigid body onto the motions a new pivot allows (plan
# F11/F12, decision D-MB11, work package J-MB14).
#
# A body with spatial inertia `M` (6x6, SPD, expressed at the **new pivot frame**) moves with
# the twist `V⁻` at that frame when the pivot engages. The pivot allows the motions spanned
# by the columns of `S` (6xn, the allowed-motion basis) and holds the directions of `C`
# (6x(6-n)): the allowed twists satisfy `Cᵀ S = 0`, i.e. `C` spans the orthogonal complement
# of `S` (the held twist components), and the constraint impulse is a wrench `C λ`. It solves
#
#     M (V⁺ - V⁻) = C λ,        Cᵀ V⁺ = 0,
#
# which gives the two equivalent forms (the corrected F12 map; the first-order guess
# `V⁻ - S (Sᵀ M S)⁻¹ Sᵀ V⁻` does not satisfy `Sᵀ M V⁺ = Sᵀ M V⁻`):
#
#     V⁺ = S (Sᵀ M S)⁻¹ Sᵀ M V⁻  =  V⁻ - M⁻¹ C (Cᵀ M⁻¹ C)⁻¹ Cᵀ V⁻ .
#
# `Sᵀ M V⁺ = Sᵀ M V⁻` holds because `Sᵀ C λ = 0`: the impulse does no work along an allowed
# motion. Kinetic energy never increases: `T⁺ - T⁻ = -½ (V⁺ - V⁻)ᵀ M (V⁺ - V⁻)`.
#
# All of this is plain numeric code (no ModelingToolkit); the stdlib block
# `stdlib:contact/SwitchedJoint`'s event is checked against it in `test_switched_joint.jl`.

"""
    pivot_inertia(Mc, g) -> SMatrix{6,6}

The spatial inertia of a body at a pivot frame: `Adᵀ Mc Ad`, with `Mc` the inertia at the
body (centre of mass) frame and `g::SE3` the **pose of the pivot frame in the body frame**
(`Ad(g)` maps a pivot twist to the body twist). `Mc` and the result are SPD.
"""
function pivot_inertia(Mc::AbstractMatrix, g::SE3)
    A = Ad(g)
    return SMatrix{6,6}(transpose(A) * SMatrix{6,6}(Mc) * A)
end

"""
    impact_projection(M, S, V) -> SVector{6}

`V⁺ = S (Sᵀ M S)⁻¹ Sᵀ M V` for the allowed-motion basis `S` (6xn; `n = 0` gives the zero
twist, the face mode). `M` must be SPD (the result is exact to rounding).
"""
function impact_projection(M::AbstractMatrix, S::AbstractMatrix, V::AbstractVector)
    size(M) == (6, 6) || throw(ArgumentError("impact_projection: M must be 6x6, got $(size(M))"))
    size(S, 1) == 6 || throw(ArgumentError("impact_projection: S must have 6 rows, got $(size(S))"))
    length(V) == 6 || throw(ArgumentError("impact_projection: V must have 6 entries"))
    Mm = Matrix{Float64}(M)
    isposdef(Symmetric(Mm)) ||
        throw(ArgumentError("impact_projection: M is not symmetric positive definite"))
    n = size(S, 2)
    n == 0 && return SVector{6,Float64}(zeros(6))
    Sm = Matrix{Float64}(S)
    Vm = Vector{Float64}(V)
    return SVector{6,Float64}(Sm * ((transpose(Sm) * Mm * Sm) \ (transpose(Sm) * Mm * Vm)))
end

"""
    impact_projection_complement(M, C, V) -> SVector{6}

The equivalent constraint form `V - M⁻¹ C (Cᵀ M⁻¹ C)⁻¹ Cᵀ V` with `C` (6xk) the constrained
directions (`k = 0` leaves `V` unchanged, the free mode)."""
function impact_projection_complement(M::AbstractMatrix, C::AbstractMatrix, V::AbstractVector)
    Vm = Vector{Float64}(V)
    size(C, 2) == 0 && return SVector{6,Float64}(Vm)
    Mm = Matrix{Float64}(M)
    Cm = Matrix{Float64}(C)
    MiC = Mm \ Cm
    return SVector{6,Float64}(Vm - MiC * ((transpose(Cm) * MiC) \ (transpose(Cm) * Vm)))
end

"""    kinetic_energy(M, V) -> Float64

`½ Vᵀ M V`."""
kinetic_energy(M::AbstractMatrix, V::AbstractVector) =
    0.5 * dot(Vector{Float64}(V), Matrix{Float64}(M) * Vector{Float64}(V))

"""
    switched_modes -> Vector{Symbol}

The modes of `stdlib:contact/SwitchedJoint` in code order (`0, 1, 2, 3`): `:free`, `:corner`
(the three rotations are allowed), `:edge` (a rotation about the pivot-frame z axis is
allowed) and `:face` (nothing is allowed).
"""
const switched_modes = [:free, :corner, :edge, :face]

"""
    switched_basis(mode) -> (S, C)

The allowed-motion basis `S` (6xn) and the constrained directions `C` (6x(6-n)) of a
`SwitchedJoint` mode in the pivot frame (twist order `[ω; v]`): `mode` is the code `0..3` or
the symbol of [`switched_modes`](@ref). The columns are unit coordinate vectors, so `[S C] = I`.
"""
function switched_basis(mode::Integer)
    allowed = mode == 0 ? (1:6) : mode == 1 ? (1:3) : mode == 2 ? (3:3) : mode == 3 ? (1:0) :
        throw(ArgumentError("switched_basis: mode must be 0..3, got $mode"))
    I6 = Matrix{Float64}(I, 6, 6)
    cons = setdiff(1:6, allowed)
    return I6[:, collect(allowed)], I6[:, cons]
end
function switched_basis(mode::Symbol)
    k = findfirst(==(mode), switched_modes)
    k === nothing && throw(ArgumentError("switched_basis: unknown mode $mode"))
    return switched_basis(k - 1)
end
