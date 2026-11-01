"""
    BGSimFEM

Offline finite element tooling for bg-sim's FEM-based flexible bodies: mesh a part (Gmsh,
primitives / CSG / STEP), assemble linear-elastic K and M (Ferrite, quadratic tetrahedra), tie
the attachment interfaces to 6-dof frames (RBE2), reduce with Craig–Bampton (interface 1 is the
body's reference frame), compute the floating-frame inertia invariants and the geometric
stiffening terms, validate the reduction against the full FE model, and write the reduced-model
file read by `stdlib:spatial/ModalBody3D` plus a GLB of the part with one morph target per mode
for the 3D viewer.

The heavy dependencies (Ferrite, Gmsh, KrylovKit) live in this separate project and never in the
core `BGSim` package: the simulator only reads the JSON file this tool writes.

    julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl part.json
"""
module BGSimFEM

using LinearAlgebra
using SparseArrays
using Printf
using Ferrite
using FerriteGmsh
using Gmsh: gmsh
import KrylovKit
import JSON3

export Material, mesh_part, assemble, make_interfaces, to_reference_frame, craig_bampton,
    validate!, reduce_part, write_modal_body, write_glb, read_glb, frequencies_hz,
    linearized_free, visual_for, modal_body_dict, ReducedModel, Interface, validate_attached!,
    attached_mass_matrix

include("geometry.jl")
include("fe.jl")
include("interfaces.jl")
include("reduce.jl")
include("output.jl")
include("spec.jl")

end
