# The flattened model (plan 5.1): what `BGSim.Compile.flatten` produces and what the
# causality pass (J2.4), the unit-factor pass (J2.5) and the lowering (J1.5) consume.
#
# Design rules:
#
# * Every variable is scalar. An array declaration `Vec{N}` becomes `x[1] ... x[N]` and a
#   matrix `Mat{N,M}` becomes `x[1,1] ... x[N,M]` (row-major), because static sizes are a
#   language principle and the lowering creates one MTK variable per scalar. `id` is the
#   plan 3.1 signal id, port fields use a dot: `Motor1/shaft.e`.
# * Expressions stay in the front-end AST (`BGSim.Name`, `BGSim.Field`, ...), with every
#   name fully qualified. `Field(Name(:var"Motor1/shaft"), :e)` is kept structured so that
#   the causality pass can tell a port field from a variable.
# * `Origin` is the provenance of every flat object: the instance path, the block reference
#   and the source range inside that block, plus the editor node and connection ids. The
#   first three are plan 5.1; the last two make model-level diagnostics highlight the right
#   canvas element (plan 3.4).
# * The bond graph is kept as `junctions` with their bonds (plan 5.4/5.7: SCAP works on it),
#   the editor metadata as `connections`, and the adopted domains as `domains` (plan 5.6).

"""
    Flat

The flat-model IR of plan section 5.1, produced by [`BGSim.Compile.flatten`](@ref).
"""
module Flat

import ..BGSim
import ..BGSim: SourceRange, Diagnostic, diag
import ..BGSim.Units
import ..BGSim.Units: Dims, unit_string

"""    Origin(path, block, range, node, connection, kind)

Where a flat object came from. `path` is the instance path (`"Plant/Motor1"`; `nothing` for
a model-wide object), `block` the block reference, `range` the source range inside that
block (`nothing` for generated equations) and `node`/`connection` the editor ids, so a
model-level diagnostic can highlight the canvas (plan 3.4). `kind` says which pass made it:
`:block`, `:bond`, `:wire`, `:signal`, `:junction`, `:parameter`.
"""
struct Origin
    path::Union{String,Nothing}
    block::Union{String,Nothing}
    range::Union{SourceRange,Nothing}
    node::Union{String,Nothing}
    connection::Union{String,Nothing}
    kind::Symbol
end

function Origin(;
    path = nothing,
    block = nothing,
    range = nothing,
    node = nothing,
    connection = nothing,
    kind = :block,
)
    return Origin(
        path === nothing ? nothing : String(path),
        block === nothing ? nothing : String(block),
        range,
        node === nothing ? nothing : String(node),
        connection === nothing ? nothing : String(connection),
        kind,
    )
end

"""    FlatVar(id, kind, type, unit, start, attrs, origin)

One scalar unknown. `kind` is the plan 3.5 signal kind (`:state`, `:algebraic`, `:input`,
`:output` or `:port`), `type` the element type (`:Real`, `:Int`, `:Bool`), `unit` a
[`Units.Dims`](@ref) or `nothing` for a wildcard, `start` the initial value (`nothing` for
an algebraic unknown and for a state without a start), and `attrs` the declaration's
attributes (`:min`, `:max`, `:unit`, ...). `kind` is mutable only because domain adoption
(plan 5.6) fixes a `Generic` port's unit after the port was created; nothing else writes a
`FlatVar`.
"""
mutable struct FlatVar
    id::String
    kind::Symbol
    type::Symbol
    unit::Union{Dims,Nothing}
    start::Any
    attrs::Dict{Symbol,Any}
    origin::Origin
end

"""    FlatParam(id, name, value, type, unit, attrs, origin)

One scalar parameter with its bound value. A `Vec{N}` parameter expands to `name[1] ...
name[N]`, each with its own value, because decision D4 keeps every `@parameters` entry as a
runtime MTK parameter and the lowering wants one scalar parameter per element."""
struct FlatParam
    id::String
    name::String
    value::Any
    type::Symbol
    unit::Union{Dims,Nothing}
    attrs::Dict{Symbol,Any}
    origin::Origin
end

"""    FlatEq(lhs, rhs, origin)

One scalar equation `lhs ~ rhs` in the front-end AST with fully qualified names."""
struct FlatEq
    lhs::BGSim.Expr
    rhs::BGSim.Expr
    origin::Origin
end

"""    ConnectionInfo(id, kind, from_node, from_path, from_port, to_node, to_path, to_port,
                    domain, factor)

The editor metadata of one connection, after resolution: an endpoint that was a subsystem
face points at the internal instance it exposes. `domain` is the adopted power domain (a
`Symbol`) for a bond or wire and `nothing` for a signal; `factor` is the unit conversion the
compiler inserts (1.0 when none)."""
struct ConnectionInfo
    id::String
    kind::Symbol
    from_node::String
    from_path::String
    from_port::Union{Symbol,Nothing}
    to_node::String
    to_path::String
    to_port::Union{Symbol,Nothing}
    domain::Union{Symbol,Nothing}
    factor::Union{Float64,Nothing}
end

"""    JunctionBond(connection, node, path, port, into, flip, eids, fids)

One bond at a junction, oriented for the junction equations (plan 5.4). `into` is `true`
when the half arrow points into the junction, i.e. the connection's `to` is the junction;
the junction sign is `into ? +1 : -1`. `flip` is `true` when the attached **port** sits at
the connection's `from` end: then the bond flow `f_b` is `-port.f` (plan 5.5: `X.f = -f_b`),
so the junction emitter negates the flow expression. For a junction-to-junction bond
`port === nothing`, `flip` is `false` and `eids`/`fids` are the virtual bond variables of
that connection."""
struct JunctionBond
    connection::String
    node::String
    path::String
    port::Union{Symbol,Nothing}
    into::Bool
    flip::Bool
    eids::Vector{String}
    fids::Vector{String}
end

"""    JunctionInfo(node, path, kind, bonds)

A 0- or 1-junction with its bonds in connection order. `kind` is 0 or 1; `path` is the
junction's instance path (`J1`). The junction has no variables of its own: its `kind + 1`
equation set is the `n` constraints of plan 5.4 over the bond variables."""
mutable struct JunctionInfo
    node::String
    path::String
    kind::Int
    bonds::Vector{JunctionBond}
end

"""    InstanceInfo(path, node, ref, variables, inputs, outputs, ports, equations, unknowns,
                   connected_ports, connected_inputs)

The per-instance counts the model-level balance check ranks (plan 5.2.7) and the editor's
stats use. `unknowns` counts the instance's scalar variables, inputs, outputs and port
fields (`2` per scalar port); `equations` its flattened block equations."""
struct InstanceInfo
    path::String
    node::String
    ref::String
    variables::Int
    inputs::Int
    outputs::Int
    ports::Int
    equations::Int
    unknowns::Int
    connected_ports::Int
    connected_inputs::Int
end

"""    DerivedSignal(id, kind, unit, path, type, expr)

A recorded signal that is not an unknown: currently the power `e*f` of every power port
(decision D15). `expr` is the AST expression, so the recorder can evaluate it after
lowering without inventing a state."""
struct DerivedSignal
    id::String
    kind::Symbol
    unit::Union{Dims,Nothing}
    path::Union{String,Nothing}
    type::Symbol
    expr::BGSim.Expr
end

"""    FlatModel(name, variables, parameters, equations, initial, events, discrete,
               junctions, connections, instances, domains, unit_factors, derived, signals,
               diagnostics, stats)

The flattened model of plan 5.1. `initial`, `events` and `discrete` are empty until J2.1
(`@initial`/`@events`/`@discrete` are rejected by the J1.1 parser); `junctions` is the bond
graph SCAP reads (J2.4); `domains` and `unit_factors` are the editor maps of plan 3.6;
`signals` is the plan 3.5 recording list (D15: every unknown, every port field and every
derived power), in recording order; `stats` carries the model-wide counts for the tests and
the editor's summary."""
struct FlatModel
    name::String
    variables::Vector{FlatVar}
    parameters::Vector{FlatParam}
    equations::Vector{FlatEq}
    initial::Vector{FlatEq}
    events::Vector{Any}
    discrete::Vector{Any}
    junctions::Vector{JunctionInfo}
    connections::Vector{ConnectionInfo}
    instances::Vector{InstanceInfo}
    domains::Dict{String,String}
    unit_factors::Dict{String,Float64}
    derived::Vector{DerivedSignal}
    signals::Vector{NamedTuple}
    diagnostics::Vector{Diagnostic}
    stats::NamedTuple
end

"""    empty_model(name; diagnostics = Diagnostic[]) -> FlatModel

A model with no variables and no equations, used when the document cannot be instantiated
at all (an empty diagram, or an internal error caught by `model_check`)."""
function empty_model(name::AbstractString; diagnostics = Diagnostic[], stats = (states = 0, equations = 0))
    return FlatModel(
        String(name),
        FlatVar[],
        FlatParam[],
        FlatEq[],
        FlatEq[],
        Any[],
        Any[],
        JunctionInfo[],
        ConnectionInfo[],
        InstanceInfo[],
        Dict{String,String}(),
        Dict{String,Float64}(),
        DerivedSignal[],
        NamedTuple[],
        collect(Diagnostic, diagnostics),
        stats,
    )
end

# ---------------------------------------------------------------------------------------
# Ids and signals
# ---------------------------------------------------------------------------------------

"""    flat_id(e) -> String

The id of a qualified name expression: `Name(:var"Motor1/i")` gives `"Motor1/i"` and
`Field(Name(:var"Motor1/shaft"), :e)` gives `"Motor1/shaft.e"`."""
flat_id(e::BGSim.Name) = String(e.name)
flat_id(e::BGSim.Field) = flat_id(e.base) * "." * String(e.field)
flat_id(e::Any) = sprint(show, e)

"""    signal_namedtuple(v::FlatVar) -> NamedTuple

The plan 3.5 signal entry of one flat variable: `id`, `unit` (a string or `nothing`), `kind`,
`path`, `type`."""
function signal_namedtuple(v::FlatVar)
    return (
        id = v.id,
        unit = v.unit === nothing ? nothing : unit_string(v.unit),
        kind = String(v.kind),
        path = v.origin.path,
        type = String(v.type),
    )
end

"""    signal_namedtuple(d::DerivedSignal) -> NamedTuple

The plan 3.5 signal entry of a derived signal (the power of a port)."""
function signal_namedtuple(d::DerivedSignal)
    return (
        id = d.id,
        unit = d.unit === nothing ? nothing : unit_string(d.unit),
        kind = String(d.kind),
        path = d.path,
        type = String(d.type),
    )
end

function Base.show(io::IO, v::FlatVar)
    print(io, "FlatVar(", v.id, "::", v.kind, ")")
end

function Base.show(io::IO, p::FlatParam)
    print(io, "FlatParam(", p.id, " = ", p.value, ")")
end

function Base.show(io::IO, e::FlatEq)
    show(io, e.lhs)
    print(io, " ~ ")
    show(io, e.rhs)
end

export Origin, FlatVar, FlatParam, FlatEq, ConnectionInfo, JunctionBond, JunctionInfo,
    InstanceInfo, DerivedSignal, FlatModel, empty_model, flat_id, signal_namedtuple

end # module Flat
