# The Lie-group / screw core of multibond mechanics (plan `mech/` layer, section 5.1;
# decisions D-MB2 and D-MB3).
#
# Everything here is **angular first**: a twist is `[ω; v]` and a wrench is `[m; f]`
# (D-MB2), planar `D = 3` = `(ω, vx, vy)` / `(τ, fx, fy)`, spatial `D = 6`. A screw is a
# plain numeric value, so it composes with `StaticArrays` matrix algebra and with the
# `Vec{D}` values of the language.
#
# The module is self-contained numeric code (no ModelingToolkit): the lowering in
# `src/lower/fnmap.jl` calls these functions through the opaque `bg_*` entry points, and
# later work packages (J-MB4 .. J-MB15) use them directly from native blocks and tests.
# `NOTES.md` ("J-MB3 - Lie core") freezes the signature list.
module Mech

using StaticArrays
using LinearAlgebra: norm, isposdef, Symmetric, det, Transpose, Adjoint, Diagonal
import Base: exp, log, inv, *, +, -, size, getindex

export Screw, Twist, Wrench, SE2, SE3, Quat, CoAdjoint,
    hat, vee, skew, Ad, AdDual, ad, compose, rotation, translation,
    spatial_inertia, planar_inertia, validate_inertia, inertia_entry,
    screw, revolute_screw, prismatic_screw, joint_basis,
    quat_exp, quat_log, quat_from_rotation, quat_to_matrix, quat_rotate,
    normalise, chart, pose

include("lie.jl")
include("quat.jl")
include("se2.jl")
include("se3.jl")

end # module Mech
