"""
    BGSim

Modeling and simulation library for bg-sim: the language front end, the lowering to
ModelingToolkit, and the simulation worker.

This module is the package skeleton (milestone M0.3). It provides the verified
ModelingToolkit interop helpers that the lowering stage (plan section 5.8) is built on,
plus a `PrecompileTools` workload that warms the MTK compile and codegen path.
"""
module BGSim

using ModelingToolkit
using ModelingToolkit: t_nounits as t, D_nounits as D
using Symbolics: Num
using SymbolicIndexingInterface: getname, getu, setp
using OrdinaryDiffEqRosenbrock
using PrecompileTools: @setup_workload, @compile_workload

export mtk_variable, mtk_parameter, mtk_discrete, signal_name

include("lower/mtk.jl")
include("precompile.jl")
include("worker/server.jl")

end # module BGSim
