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

# The language front end (plan section 4).
include("syntax/ast.jl")
include("syntax/constfold.jl")
include("syntax/whitelist.jl")
include("syntax/parse.jl")
include("syntax/scopes.jl")

# Module entry points that later WPs add. The `isfile` guard only exists so that two WPs
# adding a module in parallel cannot break each other's test run; the M1 gate replaces it
# with plain `include` calls (DEC-5 in plan/STATUS.md).
for entry in ("units/units.jl", "library/library.jl")
    path = joinpath(@__DIR__, entry)
    isfile(path) && include(path)
end

# Work package J1.4: the IR and the flattening pipeline (plan 5.2, 5.4, 5.5, 5.6).
include("compile/pipeline.jl")

# Work package J1.5: expression lowering, the compiled-system cache, the run loop and the
# recorder (plan 5.8 without events/discrete, 5.10 and 5.11).
include("lower/fnmap.jl")
include("lower/mtk.jl")
include("sim/recorder.jl")
include("sim/simulate.jl")

include("precompile.jl")
include("worker/server.jl")

# Public front-end API. Do not rename these: J1.2/J1.3/J1.4 are written against them.
export parse_block, parse_blocks, check_block, block_interface, block_equations

# AST accessors (never read the fields directly).
export block_name, block_ref, block_source, block_filename, block_range, block_diagnostics
export scopes, declarations, equations, causality, ports
export decl_name, decl_type, decl_default, decl_attrs, decl_scope, decl_range,
    decl_default_text
export expr_range
export block_balance, constant_env
export type_kind, type_args, type_name, type_size, type_element, type_domain, resolve_type,
    domain_size
export causality_ports, causality_kind, causality_value
export ParsedBlock, Decl, TypeSpec, CausalityDecl

# Diagnostics.
export Diagnostic, SourceRange, SourceRef, Related, severity_of, diag, to_namedtuple,
    to_dict, from_dict, sort_diagnostics, source_kind, scope_string

# Work package J1.5: lowering and simulation.
export LowerError, CompiledModel, nonsmooth_conditions, compile_key, lower_model,
    set_parameter_values, set_start_values, clear_compile_cache!, cache_size,
    RunSettings, SimResult, simulate, output_grid

end # module BGSim
