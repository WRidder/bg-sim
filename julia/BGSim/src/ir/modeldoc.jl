# The model document IR: plan 5.1's `ModelDoc`, read from the editor's
# `models/<name>.bgmodel.json` (contract `model.schema.json`).
#
# This file is pure syntax: it turns JSON into small immutable structs and keeps the
# expression strings of parameters and starts verbatim. It does not resolve block
# references, bind constants, check anything or evaluate user text. A structurally invalid
# document (not a `bgsim.model`, no diagram, a node without a block) is rejected with an
# `ArgumentError`: the backend has already validated the document against the JSON Schema
# (plan 3.7), so a malformed document here is a programming error in the caller, not a
# diagnostic to show in the editor. Everything the *user* can get wrong inside a valid
# document (an unknown block reference, a bad expression, two sources on one input) is
# reported by `BGSim.Compile` with the plan 3.4 diagnostic shape.
#
# The parsed document keeps only what flattening and simulation need: positions, routes,
# annotations and UI state belong to the editor and are deliberately dropped.

"""    ModelPoint(x, y)

A diagram position. Kept only where the contract requires one (a subsystem's nodes carry
`position` like any other node); flattening never reads it."""
struct ModelPoint
    x::Float64
    y::Float64
end

"""    ModelEndpoint(node, port)

One end of a connection: the node id and, unless the node is a junction, the port, input or
output name."""
struct ModelEndpoint
    node::String
    port::Union{Symbol,Nothing}
end

"""    ModelConnection(id, kind, from, to, label)

A connection in the editor's terms (plan 3.3): `kind` is `:bond`, `:wire` or `:signal`;
`from`/`to` are [`ModelEndpoint`](@ref)s. The half arrow sits at `to`, so power flows from
`from` to `to` (plan 5.5)."""
struct ModelConnection
    id::String
    kind::Symbol
    from::ModelEndpoint
    to::ModelEndpoint
    label::Union{String,Nothing}
end

"""    SubsystemPort(name, kind, direction, domain, type, size, unit, frame,
                   effort_units, flow_units, node, port)

A port exposed by a subsystem (plan 3.3 `subsystemPort`). `kind` is `:signal` or `:power`;
`direction` is `:input`/`:output` for a signal port; `domain` is the power domain for a
power port. `frame` is the exposed port's reference frame (D-MB5; `nothing` is
frame-neutral) and is authoritative for the exposed port. `effort_units`/`flow_units` are
the optional per-component unit overrides of a multibond port (`nothing` when the catalog
domain supplies them). `node` and `port` name the internal endpoint the exposed face
attaches to."""
struct SubsystemPort
    name::Symbol
    kind::Symbol
    direction::Union{Symbol,Nothing}
    domain::Union{Symbol,Nothing}
    type::Symbol
    size::Vector{Int}
    unit::Union{String,Nothing}
    frame::Union{String,Nothing}
    effort_units::Union{Vector{String},Nothing}
    flow_units::Union{Vector{String},Nothing}
    node::String
    port::Symbol
end

"""    ModelNode(id, name, block_kind, ref, junction, inline_source, subsystem, params,
               constants, starts)

One node of a diagram. `block_kind` is one of

| kind | fields |
| --- | --- |
| `:ref` | `ref` is `stdlib:...` or `project:...` |
| `:junction` | `junction` is `1` or `0` |
| `:inline` | `inline_source` is the `@block ... end` text |
| `:subsystem` | `subsystem` is the nested [`ModelDiagram`](@ref) |

`params` and `starts` are expression strings, keyed by declaration name; `constants` are
plain JSON values (number, boolean, string or array)."""
struct ModelNode
    id::String
    name::String
    block_kind::Symbol
    ref::Union{String,Nothing}
    junction::Union{Int,Nothing}
    inline_source::Union{String,Nothing}
    subsystem::Any             # a ModelDiagram, or nothing (defined below)
    subsystem_ports::Vector{SubsystemPort}
    params::Dict{String,String}
    constants::Dict{String,Any}
    starts::Dict{String,String}
    position::Union{ModelPoint,Nothing}
end

"""    ModelDiagram(nodes, connections)

One diagram level: the root diagram or a subsystem's body. `nodes` and `connections` keep
the editor's order, which is the instantiation order of plan 5.2 and therefore fixes the
order of equations, signals and diagnostics."""
struct ModelDiagram
    nodes::Vector{ModelNode}
    connections::Vector{ModelConnection}
end

"""    ModelDoc(name, language, diagram, settings, plots, scene, bindings, format)

The parsed model document. `settings` is the raw JSON object (a `Dict{String,Any}`) because
the simulation stage reads `t_start`, `t_end`, `solver`, the tolerances, the output grid and
`event_limit` from it and this stage has no reason to interpret them."""
struct ModelDoc
    format::String
    language::String
    name::String
    diagram::ModelDiagram
    settings::Dict{String,Any}
    plots::Vector{Any}
    scene::Any
    bindings::Vector{Any}
end

# ---------------------------------------------------------------------------------------
# JSON helpers (JSON3.Object and plain Dict both work)
# ---------------------------------------------------------------------------------------

function _get(o, key::AbstractString, default = nothing)
    if o isa AbstractDict
        haskey(o, key) && return o[key]
        haskey(o, Symbol(key)) && return o[Symbol(key)]
        return default
    end
    hasproperty(o, Symbol(key)) || return default
    value = getproperty(o, Symbol(key))
    return value === nothing ? default : value
end

_has(o, key::AbstractString) =
    o isa AbstractDict ? (haskey(o, key) || haskey(o, Symbol(key))) :
    hasproperty(o, Symbol(key))

function _str(v, what::AbstractString)
    v isa AbstractString || throw(ArgumentError("$what must be a string, got $(typeof(v))"))
    return String(v)
end

_str_or(v, default) = v === nothing ? default : _str(v, "a string")

function _plain(v)
    if v isa AbstractDict
        return Dict{String,Any}(String(k) => _plain(x) for (k, x) in pairs(v))
    elseif v isa AbstractVector
        return Any[_plain(x) for x in v]
    else
        return v
    end
end

function _string_map(o, what::AbstractString)
    result = Dict{String,String}()
    o === nothing && return result
    o isa AbstractDict || throw(ArgumentError("$what must be an object"))
    for (k, v) in pairs(o)
        v === nothing && continue
        result[String(k)] = v isa AbstractString ? String(v) : string(v)
    end
    return result
end

function _constant_map(o, what::AbstractString)
    result = Dict{String,Any}()
    o === nothing && return result
    o isa AbstractDict || throw(ArgumentError("$what must be an object"))
    for (k, v) in pairs(o)
        result[String(k)] = _plain(v)
    end
    return result
end

function _int_vector(v, what::AbstractString)
    v === nothing && return Int[]
    v isa AbstractVector || throw(ArgumentError("$what must be an array"))
    return Int[Int(x) for x in v]
end

function _string_vector(v, what::AbstractString)
    v === nothing && return nothing
    v isa AbstractVector || throw(ArgumentError("$what must be an array"))
    return String[_str(x, what) for x in v]
end

# ---------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------

function _endpoint(e, what::AbstractString)
    e === nothing && throw(ArgumentError("$what is missing"))
    node = _str(_get(e, "node", nothing), "$what.node")
    port_value = _get(e, "port", nothing)
    port = port_value === nothing ? nothing : Symbol(_str(port_value, "$what.port"))
    return ModelEndpoint(node, port)
end

function _parse_connection(c, index::Int)
    id = _str(_get(c, "id", nothing), "connection $index id")
    kind = Symbol(_str(_get(c, "kind", nothing), "connection $id kind"))
    kind in (:bond, :wire, :signal) ||
        throw(ArgumentError("connection `$id` has unknown kind `$kind`"))
    from = _endpoint(_get(c, "from", nothing), "connection $id from")
    to = _endpoint(_get(c, "to", nothing), "connection $id to")
    label_value = _get(c, "label", nothing)
    label = label_value === nothing ? nothing : _str(label_value, "connection $id label")
    return ModelConnection(id, kind, from, to, label)
end

function _parse_subsystem_port(p, what::AbstractString)
    name = Symbol(_str(_get(p, "name", nothing), "$what.name"))
    kind = Symbol(_str(_get(p, "kind", nothing), "$what.kind"))
    kind in (:signal, :power) || throw(ArgumentError("$what has unknown kind `$kind`"))
    direction_value = _get(p, "direction", nothing)
    direction = direction_value === nothing ? nothing : Symbol(_str(direction_value, "$what.direction"))
    domain_value = _get(p, "domain", nothing)
    domain = domain_value === nothing ? nothing : Symbol(_str(domain_value, "$what.domain"))
    type = Symbol(_str(_get(p, "type", "Real"), "$what.type"))
    size = _int_vector(_get(p, "size", nothing), "$what.size")
    unit_value = _get(p, "unit", nothing)
    unit = unit_value === nothing ? nothing : _str(unit_value, "$what.unit")
    frame_value = _get(p, "frame", nothing)
    frame = frame_value === nothing ? nothing : _str(frame_value, "$what.frame")
    effort_units = _string_vector(_get(p, "effortUnits", nothing), "$what.effortUnits")
    flow_units = _string_vector(_get(p, "flowUnits", nothing), "$what.flowUnits")
    node = _str(_get(p, "node", nothing), "$what.node")
    port = Symbol(_str(_get(p, "port", nothing), "$what.port"))
    return SubsystemPort(name, kind, direction, domain, type, size, unit, frame,
        effort_units, flow_units, node, port)
end

function _parse_node(n, index::Int)
    id = _str(_get(n, "id", nothing), "node $index id")
    name = _str(_get(n, "name", nothing), "node $id name")
    block = _get(n, "block", nothing)
    block === nothing && throw(ArgumentError("node `$id` has no block"))

    block_kind = :ref
    ref = nothing
    junction = nothing
    inline_source = nothing
    subsystem = nothing
    subsystem_ports = SubsystemPort[]

    if _has(block, "ref")
        block_kind = :ref
        ref = _str(_get(block, "ref", nothing), "node $id block.ref")
    elseif _has(block, "junction")
        block_kind = :junction
        text = _str(_get(block, "junction", nothing), "node $id block.junction")
        junction = try
            parse(Int, text)
        catch
            throw(ArgumentError("node `$id` has junction type `$text`; expected \"0\" or \"1\""))
        end
        junction in (0, 1) ||
            throw(ArgumentError("node `$id` has junction type `$text`; expected \"0\" or \"1\""))
    elseif _has(block, "inline")
        block_kind = :inline
        inline = _get(block, "inline", nothing)
        inline_source = _str(_get(inline, "source", nothing), "node $id block.inline.source")
    elseif _has(block, "subsystem")
        block_kind = :subsystem
        sub = _get(block, "subsystem", nothing)
        ports = _get(sub, "ports", nothing)
        ports === nothing || (subsystem_ports = SubsystemPort[
            _parse_subsystem_port(p, "node $id subsystem port $k") for
            (k, p) in enumerate(ports)
        ])
        sub_diagram = _get(sub, "diagram", nothing)
        sub_diagram === nothing &&
            throw(ArgumentError("node `$id` has a subsystem without a diagram"))
        subsystem = _parse_diagram(sub_diagram, "node $id subsystem")
    else
        throw(ArgumentError("node `$id` has a block that is not a ref, junction, inline or subsystem"))
    end

    position_value = _get(n, "position", nothing)
    position = nothing
    if position_value !== nothing
        position = ModelPoint(
            Float64(_get(position_value, "x", 0.0)),
            Float64(_get(position_value, "y", 0.0)),
        )
    end

    return ModelNode(
        id,
        name,
        block_kind,
        ref,
        junction,
        inline_source,
        subsystem,
        subsystem_ports,
        _string_map(_get(n, "params", nothing), "node $id params"),
        _constant_map(_get(n, "constants", nothing), "node $id constants"),
        _string_map(_get(n, "starts", nothing), "node $id starts"),
        position,
    )
end

function _parse_diagram(d, what::AbstractString = "diagram")
    d === nothing && throw(ArgumentError("the model has no $what"))
    nodes_value = _get(d, "nodes", nothing)
    connections_value = _get(d, "connections", nothing)
    nodes_value === nothing && throw(ArgumentError("$what has no nodes"))
    connections_value === nothing && throw(ArgumentError("$what has no connections"))
    nodes = ModelNode[
        _parse_node(n, k) for (k, n) in enumerate(nodes_value)
    ]
    connections = ModelConnection[
        _parse_connection(c, k) for (k, c) in enumerate(connections_value)
    ]
    ids = Set{String}()
    for node in nodes
        node.id in ids && throw(ArgumentError("duplicate node id `$(node.id)` in $what"))
        push!(ids, node.id)
    end
    names = Set{String}()
    for node in nodes
        node.name in names &&
            throw(ArgumentError("duplicate node name `$(node.name)` in $what"))
        push!(names, node.name)
    end
    conn_ids = Set{String}()
    for c in connections
        c.id in conn_ids && throw(ArgumentError("duplicate connection id `$(c.id)` in $what"))
        push!(conn_ids, c.id)
    end
    return ModelDiagram(nodes, connections)
end

"""    parse_model(path_or_dict) -> ModelDoc

Read a model document from a file path, a JSON string, a `JSON3.Object` or a plain
`Dict`. The `format` must be `"bgsim.model"`; `language` defaults to `"0.1.0"` (the only
language version of M1). Nodes, connections and ids are validated structurally; anything
semantic is left to `BGSim.Compile.model_check`.
"""
function parse_model(source::AbstractString)
    if isfile(source)
        return parse_model(JSON3.read(read(source, String)))
    end
    return parse_model(JSON3.read(source))
end

function parse_model(obj::AbstractDict)
    format = _str_or(_get(obj, "format", nothing), "bgsim.model")
    format == "bgsim.model" ||
        throw(ArgumentError("not a bgsim model: format is `$format`"))
    name = _str(_get(obj, "name", nothing), "model name")
    isempty(name) && throw(ArgumentError("the model name must not be empty"))
    language = _str_or(_get(obj, "language", nothing), "0.1.0")
    diagram = _parse_diagram(_get(obj, "diagram", nothing))
    settings = _plain(_get(obj, "settings", nothing))
    settings isa AbstractDict || (settings = Dict{String,Any}())
    plots_value = _get(obj, "plots", nothing)
    plots = plots_value === nothing ? Any[] : _plain(plots_value)
    scene = _plain(_get(obj, "scene", nothing))
    bindings_value = _get(obj, "bindings", nothing)
    bindings = bindings_value === nothing ? Any[] : _plain(bindings_value)
    return ModelDoc(
        format,
        language,
        name,
        diagram,
        settings,
        Any[plots...],
        scene,
        Any[bindings...],
    )
end
