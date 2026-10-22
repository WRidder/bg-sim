# The IR block definition (plan 5.1).
#
# `BlockDef` already exists in `src/library/library.jl` (work package J1.3): it is the
# parsed, checked and catalogued block, and duplicating it here would make two types with
# the same name and different fields. The IR therefore owns the *alias*, not the struct:
# every later stage (flattening, causality, lowering) refers to `BGSim.IR.BlockDef` and
# gets the very object the library cache returned, diagnostics and all.
#
# `modeldoc.jl` (the model JSON -> `ModelDoc`) is included here so that `BGSim.IR` is one
# module with one entry file; `src/compile/pipeline.jl` includes this file exactly once.

"""
    IR

The intermediate representation of plan section 5.1:

| type | meaning |
| --- | --- |
| [`BlockDef`](@ref) | a parsed and checked library block (the J1.3 type, aliased) |
| [`ModelDoc`](@ref) | the editor's model JSON, parsed into plain Julia structs |
| `ModelDiagram`, `ModelNode`, `ModelConnection` | the diagram tree |
| [`SubsystemPort`](@ref) | an exposed port of a subsystem node |

The model document is deliberately *syntax only*: it holds ids, names, block references,
expression strings and the settings blob. Resolving block references, binding constants and
turning the diagram into flat equations is `BGSim.Compile`'s job.
"""
module IR

import ..BGSim
import JSON3

# J1.3 owns the struct; the IR re-exports the same type under the plan 5.1 name.
const BlockDef = BGSim.Library.BlockDef

include("modeldoc.jl")

end # module IR
