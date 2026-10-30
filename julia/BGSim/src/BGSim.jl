"""
    BGSim

Modeling and simulation library for bg-sim: the language front end, the lowering to
ModelingToolkit, and the simulation worker.

Milestone M0.3 provides the verified ModelingToolkit interop helpers that the lowering stage
(plan section 5.8) is built on, plus a `PrecompileTools` workload that warms the MTK compile
and codegen path. Work package J1.1 adds the language front end: `src/diagnostics.jl` (the
plan 3.4 diagnostic contract) and `src/syntax/` (the parser, the AST, the whitelist and the
block-level checks).
"""
module BGSim

using ModelingToolkit
using ModelingToolkit: t_nounits as t, D_nounits as D, SymbolicContinuousCallback
using Symbolics: Num
import Symbolics
using SymbolicIndexingInterface: getname, getu, getp, setp
using OrdinaryDiffEqRosenbrock
import OrdinaryDiffEqTsit5, OrdinaryDiffEqBDF, OrdinaryDiffEqVerner
using PrecompileTools: @setup_workload, @compile_workload
using JuliaSyntax

export mtk_variable, mtk_parameter, mtk_discrete, signal_name

# The diagnostics contract (plan 3.4).
include("diagnostics.jl")

# Work package J-MB3: the Lie-group / screw core (`mech/`: SE2, SE3, quaternions, Ad/ad,
# exp/log, spatial inertia). Numeric only; the lowering calls it through `fnmap.jl`.
include("mech/mech.jl")
using .Mech

# The language front end (plan section 4).
include("syntax/ast.jl")
include("syntax/constfold.jl")
include("syntax/whitelist.jl")
include("syntax/parse.jl")
include("syntax/scopes.jl")

# Work packages J1.2 (units) and J1.3 (library loader, catalog, M1 stdlib). The M1 gate
# replaces the temporary `isfile` guard of DEC-5 with these plain includes.
include("units/units.jl")
include("library/library.jl")
include("syntax/watch.jl")

# Work package J1.4: the IR and the flattening pipeline (plan 5.2, 5.4, 5.5, 5.6).
include("compile/pipeline.jl")

# Work package J1.5: expression lowering, the compiled-system cache, the run loop and the
# recorder (plan 5.8 without events/discrete, 5.10 and 5.11).
include("lower/fnmap.jl")
include("lower/mtk.jl")
include("sim/recorder.jl")
include("sim/simulate.jl")
include("sim/scheduler.jl")
include("sim/debug.jl")
include("sim/hooks.jl")
include("sim/watch.jl")
include("compile/explain.jl")

include("precompile.jl")
include("worker/server.jl")

# Public front-end API. Do not rename these: J1.2/J1.3/J1.4 are written against them.
export parse_block, parse_blocks, check_block, block_interface, block_equations

# AST accessors (never read the fields directly).
export block_name, block_ref, block_source, block_filename, block_range, block_diagnostics
export scopes, declarations, equations, causality, ports, components, connections, observations
export decl_name, decl_type, decl_default, decl_attrs, decl_scope, decl_range,
    decl_default_text
export expr_range
export block_balance, constant_env
export type_kind, type_args, type_name, type_size, type_element, type_domain, resolve_type,
    domain_size
export causality_ports, causality_kind, causality_value
export component_name, component_block, component_kwargs
export observation_name, observation_field, observation_target
export portref_instance, portref_port, connect_from, connect_to
export ParsedBlock, Decl, TypeSpec, CausalityDecl, ComponentDecl, PortRef, ConnectDecl,
    ObservationDecl

# Diagnostics.
export Diagnostic, SourceRange, SourceRef, Related, severity_of, diag, to_namedtuple,
    to_dict, from_dict, sort_diagnostics, source_kind, scope_string

# Work package J1.5: lowering and simulation. J2.8 adds the compile-cache introspection and
# policy API (`compile_build_count`, `compile_cache_limit`).
export LowerError, CompiledModel, nonsmooth_conditions, compile_key, lower_model,
    set_parameter_values, set_start_values, clear_compile_cache!, cache_size,
    compile_build_count, compile_cache_limit,
    RunSettings, SimResult, simulate, output_grid

# Work package J-MB3: the screw core (also reachable as `BGSim.Mech`). `exp`, `log`, `inv`
# and `*` are extended on the pose/screw types rather than exported, so they stay Base's
# functions and `exp(1.0)` still means what it always meant.
export Screw, Twist, Wrench, SE2, SE3, Quat, CoAdjoint
export hat, vee, skew, Ad, AdDual, ad, rotation, translation
export spatial_inertia, planar_inertia, validate_inertia
export screw, revolute_screw, prismatic_screw, joint_basis
export quat_exp, quat_log, quat_from_rotation, quat_to_matrix, quat_rotate, normalise


# Work package J-MB15: joint-chain records, loader, lumpInto, inverse dynamics.
using .Library: LinkRecord, JointRecord, JointChain, joint_pose, load_chain, chain_model, lumpInto,
    inverse_dynamics, gravity_compensation
export LinkRecord, JointRecord, JointChain, joint_pose, load_chain, chain_model, lumpInto,
    inverse_dynamics, gravity_compensation

end # module BGSim
