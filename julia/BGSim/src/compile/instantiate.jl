# Instantiation and flattening (plan 5.2): resolve every node's block, bind its constants
# (so every size is fixed before anything is created), expand subsystems with path
# prefixes, bind parameter and start expressions through the front end, create the
# scalarized variables, and flatten the block equations with fully qualified names.
#
# Nothing here reports a connection problem: that is `connect.jl`. Nothing here decides a
# domain: that is `domains.jl`. The one shared context is `Builder`, which owns the flat
# variables, parameters, equations, diagnostics and the raw (resolved) connection list.
#
# Expression strings in the model JSON are parsed with the *same* front end, by wrapping
# them in a throwaway `@block` whose single `@parameters` declaration carries the value.
# That gives the exact same tokenizer, whitelist and name checks as block source, with a
# real `SourceRange`; the only mapping applied is E000 -> E001, because a syntax error in a
# model-level value is reported as a declaration error (plan 5.2.4).

import ..BGSim: Name, Field, Lit, Call, BinOp, UnOp, Index, VectorLit, MatrixLit, IfElse,
    Comparison, BoolOp, Equation, IfEquation, ForEquation, EqBranch, try_eval_const,
    eval_const, ConstFoldError, constant_env, type_scalar_count

"""    PortInfo(node, path, name, domain, size, eids, fids, qname, range, frame)

One power port of one instance. `domain` is the *declared* domain (`:Generic` for a bond
graph element); `size` is the domain's size (`3` for Planar, `6` for Spatial, `1` otherwise);
`eids`/`fids` are the flat variable ids of the effort and flow, one per component. `qname`
is the qualified port name used as the base of a `Field` expression (`"Motor1/shaft"`).
`frame` is the port's declared reference frame (D-MB5, unqualified catalog name) or
`nothing` for a frame-neutral port."""
struct PortInfo
    node::String
    path::String
    name::Symbol
    domain::Symbol
    size::Int
    eids::Vector{String}
    fids::Vector{String}
    qname::String
    range::BGSim.SourceRange
    frame::Union{String,Nothing}
end

"""    RawEndpoint(node, path, port, kind, face)

One endpoint of a connection after resolving subsystem faces: `kind` is `:power`, `:input`,
`:output`, `:junction` or `:unknown`. `path` is the *internal* instance path (for a
subsystem face, the leaf instance it exposes); `node` is the editor id of that leaf node.
`face` is `(subsystem path, exposed port name)` when the endpoint was reached through a
subsystem boundary, and `nothing` for an ordinary instance port (D-MB5: the face's frame is
authoritative for the exposed port)."""
struct RawEndpoint
    node::String
    path::String
    port::Union{Symbol,Nothing}
    kind::Symbol
    face::Union{Nothing,Tuple{String,Symbol}}
end

RawEndpoint(node, path, port, kind) = RawEndpoint(node, path, port, kind, nothing)

"""    RawConnection(conn, from, to, diagram)

A model connection with both ends resolved, collected while the diagrams are walked but not
yet checked. `diagram` is the path prefix of the diagram it belongs to (`""` at the root)."""
struct RawConnection
    conn::IR.ModelConnection
    from::RawEndpoint
    to::RawEndpoint
    diagram::String
end

"""    BlockState

The instantiated state of one library/inline block instance: its declarations (so a name
looks up its flat ids), the scalar ids and shapes per declaration, the port table, the
bound constants, and the counts the balance check uses. `adopted` is the power domain
domain adoption (5.6) gave the instance; `:Generic` until then."""
mutable struct BlockState
    path::String
    node::String
    ref::String
    block::IR.BlockDef
    pb::BGSim.ParsedBlock
    consts::Dict{Symbol,Any}
    domain::Symbol
    adopted::Symbol
    decls::Dict{Symbol,BGSim.Decl}
    ids::Dict{Symbol,Vector{String}}
    shapes::Dict{Symbol,Tuple{Vararg{Int}}}
    units::Dict{Symbol,Union{Dims,Nothing}}
    ports::Dict{Symbol,PortInfo}
    var_count::Int
    eq_count::Int
end

"""    Builder

The shared flattening context. It is created once by `flatten`, filled by `instantiate.jl`,
read by `connect.jl`/`domains.jl`/`junctions.jl`/`balance.jl`, and finally frozen into a
`FlatModel`."""
mutable struct Builder
    md::IR.ModelDoc
    project_dir::Union{String,Nothing}
    stdlib::Union{Dict{String,IR.BlockDef},Nothing}
    project::Union{Dict{String,IR.BlockDef},Nothing}
    diagnostics::Vector{Diagnostic}
    vars::Vector{Flat.FlatVar}
    var_index::Dict{String,Int}
    params::Vector{Flat.FlatParam}
    param_index::Dict{String,Int}
    equations::Vector{Flat.FlatEq}
    states::Vector{BlockState}
    state_by_path::Dict{String,BlockState}
    port_at::Dict{Tuple{String,Symbol},PortInfo}
    junctions::Vector{Flat.JunctionInfo}
    junction_by_path::Dict{String,Int}
    raw::Vector{RawConnection}
    boundary::Dict{String,Dict{Symbol,RawEndpoint}}
    boundary_nodes::Dict{String,String}
    boundary_ports::Dict{Tuple{String,Symbol},IR.SubsystemPort}
    composite_stack::Vector{String}
    param_alias::Dict{Tuple{String,Symbol},String}
    observed::Vector{Flat.DerivedSignal}
    nodes_total::Int
    conns_total::Int
    power_signals::Dict{String,Flat.DerivedSignal}
end

function Builder(md::IR.ModelDoc, project_dir::Union{String,Nothing})
    return Builder(
        md,
        project_dir,
        nothing,
        nothing,
        Diagnostic[],
        Flat.FlatVar[],
        Dict{String,Int}(),
        Flat.FlatParam[],
        Dict{String,Int}(),
        Flat.FlatEq[],
        BlockState[],
        Dict{String,BlockState}(),
        Dict{Tuple{String,Symbol},PortInfo}(),
        Flat.JunctionInfo[],
        Dict{String,Int}(),
        RawConnection[],
        Dict{String,Dict{Symbol,RawEndpoint}}(),
        Dict{String,String}(),
        Dict{Tuple{String,Symbol},IR.SubsystemPort}(),
        String[],
        Dict{Tuple{String,Symbol},String}(),
        Flat.DerivedSignal[],
        0,
        0,
        Dict{String,Flat.DerivedSignal}(),
    )
end

# ---------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------

_join(prefix::String, name::Union{AbstractString,Symbol}) =
    isempty(prefix) ? String(name) : prefix * "/" * String(name)

_qname(st::BlockState, name::Symbol) = st.path * "/" * String(name)

function _report!(
    b::Builder,
    st::BlockState;
    code,
    message,
    range = nothing,
    hint = nothing,
    scope = nothing,
    connection = nothing,
    path = st.path,
    node = st.node,
    block = st.ref,
)
    source = range === nothing ? nothing :
             BGSim.SourceRef(BGSim.source_kind(st.ref), st.ref, range)
    push!(
        b.diagnostics,
        diag(
            code,
            message;
            hint = hint,
            path = path,
            block = block,
            scope = scope,
            source = source,
            node = node,
            connection = connection,
        ),
    )
    return nothing
end

function _report_node!(
    b::Builder,
    md_node::IR.ModelNode,
    path::String,
    ref::Union{String,Nothing};
    code,
    message,
    hint = nothing,
    connection = nothing,
)
    push!(
        b.diagnostics,
        diag(
            code,
            message;
            hint = hint,
            path = path,
            block = ref,
            node = md_node.id,
            connection = connection,
        ),
    )
    return nothing
end

_retarget(d::Diagnostic, path::String, ref::String, node::String) = diag(
    d.code,
    d.message;
    hint = d.hint,
    path = path,
    block = ref,
    scope = d.scope,
    source = d.source,
    node = node,
    connection = d.connection,
    related = d.related,
    severity = d.severity,
)

function _add_var!(b::Builder, v::Flat.FlatVar)
    haskey(b.var_index, v.id) && return nothing
    push!(b.vars, v)
    b.var_index[v.id] = length(b.vars)
    return nothing
end

function _add_param!(b::Builder, p::Flat.FlatParam)
    haskey(b.param_index, p.id) && return nothing
    push!(b.params, p)
    b.param_index[p.id] = length(b.params)
    return nothing
end

var_by_id(b::Builder, id::AbstractString) =
    haskey(b.var_index, id) ? b.vars[b.var_index[id]] : nothing

function _shape_of(t::BGSim.TypeSpec, consts::AbstractDict)
    size = BGSim.type_size(t, consts)
    size === nothing && return nothing
    return Tuple(Int.(size))
end

function _element_ids(qname::String, shape::Tuple{Vararg{Int}})
    isempty(shape) && return String[qname]
    if length(shape) == 1
        return String[qname * "[" * string(i) * "]" for i in 1:shape[1]]
    end
    ids = String[]
    for i in 1:shape[1], j in 1:shape[2]
        push!(ids, qname * "[" * string(i) * "," * string(j) * "]")
    end
    return ids
end

_shape_length(shape::Tuple{Vararg{Int}}) = isempty(shape) ? 1 : prod(shape)

# Row-major scalar index of one element of a shape.
function _shape_element(shape::Tuple{Vararg{Int}}, i::Int, j::Int = 1)
    length(shape) <= 1 && return i
    return (i - 1) * shape[2] + j
end

# ---------------------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------------------

function _load_stdlib!(b::Builder)
    b.stdlib === nothing &&
        (b.stdlib = Dict{String,IR.BlockDef}(x.ref => x for x in Library.load_stdlib()))
    return b.stdlib
end

function _load_project!(b::Builder)
    if b.project === nothing
        dir = b.project_dir === nothing ? nothing : joinpath(b.project_dir, "library")
        b.project = dir === nothing ? Dict{String,IR.BlockDef}() :
                    Dict{String,IR.BlockDef}(x.ref => x for x in Library.load_project_library(dir))
    end
    return b.project
end

"""
    resolve_block(b, node, path) -> Union{BlockDef,Nothing}

Load the block a node refers to. `stdlib:` comes from the shipped library, `project:` from
`<project_dir>/library/`, and `inline:` must carry its source (a bare `inline:<id>` ref has
none and is unknown). An unknown reference is E101 — the model cannot be assembled, and
E101 is the model-assembly code of the spec table (`E102` is specifically a mismatch *on a
connection*). The decision is documented in the WP report.
"""
function resolve_block(b::Builder, node::IR.ModelNode, path::String)
    ref = something(node.ref, "")
    if node.block_kind == :inline
        block = Library.load_block(
            something(node.inline_source, "");
            ref = "inline:" * node.id,
            path = nothing,
        )
        return _check_block(b, block, node, path)
    elseif startswith(ref, "stdlib:")
        block = get(_load_stdlib!(b), ref, nothing)
        block === nothing && return _unknown_block!(b, node, path, ref)
        return _check_block(b, block, node, path)
    elseif startswith(ref, "project:")
        block = get(_load_project!(b), ref, nothing)
        block === nothing && return _unknown_block!(b, node, path, ref)
        return _check_block(b, block, node, path)
    else
        return _unknown_block!(b, node, path, ref)
    end
end

function _unknown_block!(b::Builder, node::IR.ModelNode, path::String, ref::String)
    _report_node!(
        b,
        node,
        path,
        isempty(ref) ? nothing : ref;
        code = "E101",
        message = "unknown block reference `" * (isempty(ref) ? "?" : ref) * "` on `$(node.name)`",
        hint = "pick a block from the catalog, or add `library/Name.jl` to the project library",
    )
    return nothing
end

function _check_block(b::Builder, block::IR.BlockDef, node::IR.ModelNode, path::String)
    for d in block.diagnostics
        push!(b.diagnostics, _retarget(d, path, block.ref, node.id))
    end
    if any(d -> d.severity == "error", block.diagnostics)
        return nothing
    end
    return block
end

# ---------------------------------------------------------------------------------------
# Constants (bound before anything else, so every size is fixed: plan 5.2.2)
# ---------------------------------------------------------------------------------------

function _bind_constants!(
    b::Builder,
    st::BlockState,
    node::IR.ModelNode,
)
    consts = constant_env(st.pb)
    for (key, value) in node.constants
        name = Symbol(key)
        if !haskey(consts, name)
            _report!(
                b,
                st;
                code = "E003",
                message = "`$(st.path)` has no constant `$key`",
                hint = "declare it in `@constants` of `$(block_name_safe(st))`, or fix the spelling",
                scope = "@constants",
            )
            continue
        end
        decls = BGSim.declarations(st.pb, :constants)
        decl = findfirst(d -> BGSim.decl_name(d) == name, decls)
        if decl === nothing
            continue
        end
        d = decls[decl]
        resolved = BGSim.resolve_type(BGSim.decl_type(d), consts)
        folded = _constant_value(b, st, d, resolved, value)
        folded === nothing && continue
        consts[name] = folded
    end
    st.consts = consts
    return nothing
end

block_name_safe(st::BlockState) = String(st.block.name)

function _constant_value(
    b::Builder,
    st::BlockState,
    decl::BGSim.Decl,
    t::BGSim.TypeSpec,
    value,
)
    name = BGSim.decl_name(decl)
    parsed = value
    if value isa AbstractString
        shape = _shape_of(t, st.consts)
        shape === nothing && return nothing
        parsed = _parse_value(
            b,
            st,
            String(value),
            t,
            shape;
            what = "constant `$name`",
            scope = "@constants",
        )
        parsed === nothing && return nothing
    end
    ok, message = _check_value(parsed, t, _shape_of(t, st.consts))
    if !ok
        _report!(
            b,
            st;
            code = "E004",
            message = "invalid value for constant `$name` of `$(st.path)`: $message",
            scope = "@constants",
            hint = "constants are structural; their value fixes array sizes and loop bounds",
        )
        return nothing
    end
    # An Int constant must stay an Int (a structural size), a Real constant may widen.
    if BGSim.type_kind(t) == :Int
        return parsed isa Integer ? Int(parsed) : nothing
    elseif BGSim.type_kind(t) == :Real
        return Float64(parsed)
    else
        return parsed
    end
end

# ---------------------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------------------

function _instantiate_block!(
    b::Builder,
    node::IR.ModelNode,
    path::String,
    block::IR.BlockDef,
)
    st = BlockState(
        path,
        node.id,
        block.ref,
        block,
        block.ast,
        Dict{Symbol,Any}(),
        BGSim.Units.block_domain(block.ast),
        :Generic,
        Dict{Symbol,BGSim.Decl}(),
        Dict{Symbol,Vector{String}}(),
        Dict{Symbol,Tuple{Vararg{Int}}}(),
        Dict{Symbol,Union{Dims,Nothing}}(),
        Dict{Symbol,PortInfo}(),
        0,
        0,
    )
    for scope in (:constants, :parameters, :variables, :inputs, :outputs, :ports)
        for d in BGSim.declarations(st.pb, scope)
            st.decls[BGSim.decl_name(d)] = d
        end
    end
    _bind_constants!(b, st, node)
    _create_declarations!(b, st, node)
    _bind_parameters!(b, st, node)
    _bind_starts!(b, st, node)
    _emit_block_equations!(b, st)
    push!(b.states, st)
    b.state_by_path[path] = st
    b.nodes_total += 1
    return st
end

function _create_declarations!(b::Builder, st::BlockState, node::IR.ModelNode)
    env = BGSim.Units.unit_env(st.pb)
    ddt_names = _ddt_targets(st.pb)
    for scope in (:variables, :inputs, :outputs)
        for d in BGSim.declarations(st.pb, scope)
            name = BGSim.decl_name(d)
            t = BGSim.resolve_type(BGSim.decl_type(d), st.consts)
            shape = _shape_of(t, st.consts)
            if shape === nothing
                _report!(
                    b,
                    st;
                    code = "E005",
                    message = "the size of `$name` is not static",
                    range = BGSim.decl_range(d),
                    scope = BGSim.scope_string(scope),
                )
                shape = ()
            end
            qn = _qname(st, name)
            ids = _element_ids(qn, shape)
            unit = get(env.names, name, nothing)
            kind = if scope === :variables
                attrs = BGSim.decl_attrs(d)
                state_attr = get(attrs, :state, nothing)
                state_attr === :avoid ? :algebraic :
                (name in ddt_names ? :state : :algebraic)
            elseif scope === :inputs
                :input
            else
                :output
            end
            start = nothing
            if BGSim.decl_default(d) !== nothing
                ok, value = try_eval_const(BGSim.decl_default(d), st.consts)
                if ok
                    start = value
                end
            end
            _store_vars!(b, st, d, ids, shape, unit, kind, start)
        end
    end
    # Ports: two scalar unknowns per component, effort and flow (plan 5.5).
    for d in BGSim.ports(st.pb)
        name = BGSim.decl_name(d)
        t = BGSim.resolve_type(BGSim.decl_type(d), st.consts)
        domain = something(BGSim.type_domain(t), :Generic)
        size = BGSim.domain_size(domain)
        qport = _qname(st, name)
        eids = size == 1 ? String[qport * ".e"] :
               String[qport * ".e[" * string(k) * "]" for k in 1:size]
        fids = size == 1 ? String[qport * ".f"] :
               String[qport * ".f[" * string(k) * "]" for k in 1:size]
        for (k, id) in enumerate(eids)
            _add_var!(
                b,
                Flat.FlatVar(
                    id,
                    :port,
                    :Real,
                    BGSim.Units.effort_dims(domain),
                    nothing,
                    copy(BGSim.decl_attrs(d)),
                    Flat.Origin(; path = st.path, block = st.ref, node = st.node,
                        range = BGSim.decl_range(d), kind = :port),
                ),
            )
        end
        for (k, id) in enumerate(fids)
            _add_var!(
                b,
                Flat.FlatVar(
                    id,
                    :port,
                    :Real,
                    BGSim.Units.flow_dims(domain),
                    nothing,
                    copy(BGSim.decl_attrs(d)),
                    Flat.Origin(; path = st.path, block = st.ref, node = st.node,
                        range = BGSim.decl_range(d), kind = :port),
                ),
            )
        end
        info = PortInfo(node.id, st.path, name, domain, size, eids, fids, qport,
            BGSim.decl_range(d), get(BGSim.decl_attrs(d), :frame, nothing))
        st.ports[name] = info
        b.port_at[(st.path, name)] = info
        st.var_count += 2 * size
    end
    return nothing
end

function _store_vars!(
    b::Builder,
    st::BlockState,
    d::BGSim.Decl,
    ids::Vector{String},
    shape::Tuple{Vararg{Int}},
    unit::Union{Dims,Nothing},
    kind::Symbol,
    start,
)
    name = BGSim.decl_name(d)
    st.ids[name] = ids
    st.shapes[name] = shape
    st.units[name] = unit
    etype = BGSim.type_element(BGSim.decl_type(d))
    values = _scalar_values(start, shape)
    for (k, id) in enumerate(ids)
        _add_var!(
            b,
            Flat.FlatVar(
                id,
                kind,
                etype,
                unit,
                values === nothing ? nothing : values[k],
                copy(BGSim.decl_attrs(d)),
                Flat.Origin(; path = st.path, block = st.ref, node = st.node,
                    range = BGSim.decl_range(d), kind = :block),
            ),
        )
    end
    st.var_count += length(ids)
    return nothing
end

# A start value / default, flattened to one value per scalar element, or `nothing`.
function _scalar_values(value, shape::Tuple{Vararg{Int}})
    value === nothing && return nothing
    isempty(shape) && return Any[value]
    if length(shape) == 1
        value isa AbstractVector || return nothing
        length(value) == shape[1] || return nothing
        return Any[value[i] for i in 1:shape[1]]
    end
    if value isa AbstractMatrix
        size(value) == (shape[1], shape[2]) || return nothing
        # Row-major, the order `_element_ids` names (`x[1,1], x[1,2], ...`) and the order
        # `QValue.elems` uses. `value[i, j]` is column-major, so iterate explicitly.
        return Any[value[i, j] for i in 1:shape[1] for j in 1:shape[2]]
    end
    if value isa AbstractVector && length(value) == shape[1] &&
       all(v -> v isa AbstractVector && length(v) == shape[2], value)
        return Any[value[i][j] for i in 1:shape[1] for j in 1:shape[2]]
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Parameter and start values
# ---------------------------------------------------------------------------------------

function _bind_parameters!(b::Builder, st::BlockState, node::IR.ModelNode)
    for d in BGSim.declarations(st.pb, :parameters)
        name = BGSim.decl_name(d)
        t = BGSim.resolve_type(BGSim.decl_type(d), st.consts)
        shape = _shape_of(t, st.consts)
        if shape === nothing
            _report!(
                b,
                st;
                code = "E005",
                message = "the size of parameter `$name` is not static",
                range = BGSim.decl_range(d),
                scope = "@parameters",
            )
            continue
        end
        text = get(node.params, String(name), nothing)
        target = get(b.param_alias, (st.path, name), nothing)
        if target !== nothing
            ids = _element_ids(target, shape)
            found = all(haskey(b.param_index, id) for id in ids)
            if !found
                _report!(
                    b,
                    st;
                    code = "E003",
                    message = "parameter `$name` of `$(st.path)` aliases unknown parameter `$target`",
                    range = BGSim.decl_range(d),
                    scope = "@parameters",
                    hint = "a composite parameter is declared in the enclosing composite's `@parameters`",
                )
                continue
            end
            st.ids[name] = ids
            st.shapes[name] = shape
            st.units[name] = b.params[b.param_index[first(ids)]].unit
            continue
        end
        value = if text !== nothing
            _parse_value(
                b,
                st,
                text,
                t,
                shape;
                what = "parameter `$name`",
                scope = "@parameters",
            )
        elseif BGSim.decl_default(d) !== nothing
            ok, folded = try_eval_const(BGSim.decl_default(d), st.consts)
            if ok
                folded
            else
                _report!(
                    b,
                    st;
                    code = "E001",
                    message = "the default of parameter `$name` is not a constant expression",
                    range = BGSim.decl_range(d),
                    scope = "@parameters",
                    hint = "write a literal or a `@constants` expression",
                )
                nothing
            end
        else
            _report!(
                b,
                st;
                code = "E004",
                message = "parameter `$name` of `$(st.path)` has no value",
                range = BGSim.decl_range(d),
                scope = "@parameters",
                hint = "give it a default in the block, or set it on the instance",
            )
            nothing
        end
        value === nothing && continue
        ok, message = _check_value(value, t, shape)
        if !ok
            _report!(
                b,
                st;
                code = "E004",
                message = "invalid value for parameter `$name` of `$(st.path)`: $message",
                range = BGSim.decl_range(d),
                scope = "@parameters",
            )
            continue
        end
        ids = _element_ids(_qname(st, name), shape)
        st.ids[name] = ids
        st.shapes[name] = shape
        st.units[name] = get(BGSim.Units.unit_env(st.pb).names, name, nothing)
        values = _scalar_values(value, shape)
        for (k, id) in enumerate(ids)
            _add_param!(
                b,
                Flat.FlatParam(
                    id,
                    String(name),
                    values[k],
                    BGSim.type_element(t),
                    st.units[name],
                    copy(BGSim.decl_attrs(d)),
                    Flat.Origin(; path = st.path, block = st.ref, node = st.node,
                        range = BGSim.decl_range(d), kind = :parameter),
                ),
            )
        end
    end
    return nothing
end

function _bind_starts!(b::Builder, st::BlockState, node::IR.ModelNode)
    for (key, text) in node.starts
        name = Symbol(key)
        d = get(st.decls, name, nothing)
        if d === nothing || BGSim.decl_scope(d) != :variables
            _report!(
                b,
                st;
                code = "E003",
                message = "`$(st.path)` has no variable `$key` to give a start value",
                hint = "the start override keys the `@variables` of the block",
            )
            continue
        end
        t = BGSim.resolve_type(BGSim.decl_type(d), st.consts)
        shape = _shape_of(t, st.consts)
        shape === nothing && continue
        value = _parse_value(
            b,
            st,
            text,
            t,
            shape;
            what = "start value of `$key`",
            scope = "@variables",
        )
        value === nothing && continue
        ok, message = _check_value(value, t, shape)
        if !ok
            _report!(
                b,
                st;
                code = "E004",
                message = "invalid start value for `$key` of `$(st.path)`: $message",
                range = BGSim.decl_range(d),
                scope = "@variables",
            )
            continue
        end
        values = _scalar_values(value, shape)
        values === nothing && continue
        for (k, id) in enumerate(st.ids[name])
            v = var_by_id(b, id)
            v === nothing || (v.start = values[k])
        end
    end
    return nothing
end

"""    _parse_value(b, st, text, t, shape; what, scope) -> value or nothing

Parse and fold one model-level expression string with the front end. The string is wrapped
in a single-declaration block of the expected type so the parser, the whitelist and the
name check all see exactly what a block default sees. A parse error becomes E001 (the
plan 5.2.4 code for a bad model-level expression), an undeclared name stays E003, and a
type/shape mismatch stays E004; all of them point at the *instance* (node + path) and name
the parameter/start in the message, because the model JSON has no source range.
"""
function _parse_value(
    b::Builder,
    st::BlockState,
    text::AbstractString,
    t::BGSim.TypeSpec,
    shape::Tuple{Vararg{Int}};
    what::AbstractString,
    scope,
)
    tname = BGSim.type_name(t)
    src = "@block __ModelValue begin\n    @parameters __value::" * tname * " = " *
          String(text) * "\nend\n"
    pb = try
        BGSim.parse_block(src; filename = "__model_value", ref = "inline:__model_value")
    catch err
        _report!(
            b,
            st;
            code = "E001",
            message = "invalid $what of `$(st.path)`: " * sprint(showerror, err),
            scope = scope,
            hint = "write a constant expression such as `2.0`, `1e-3` or `[1.0, 2.0]`",
        )
        return nothing
    end
    ds = BGSim.declarations(pb, :parameters)
    if isempty(ds) || ds[1].default === nothing
        message = "invalid $what of `$(st.path)`: the expression cannot be parsed"
        for d in BGSim.block_diagnostics(pb)
            d.severity == "error" || continue
            message = "invalid $what of `$(st.path)`: " * d.message
            break
        end
        _report!(
            b,
            st;
            code = "E001",
            message = message,
            scope = scope,
            hint = "write a constant expression such as `2.0`, `1e-3` or `[1.0, 2.0]`",
        )
        return nothing
    end
    failed = false
    for d in BGSim.check_block(pb)
        d.code == "W204" && continue
        d.severity == "error" || continue
        failed = true
        code = d.code == "E000" ? "E001" : d.code
        _report!(
            b,
            st;
            code = code,
            message = "invalid $what of `$(st.path)`: " * d.message,
            hint = d.hint,
            scope = scope,
        )
    end
    failed && return nothing
    ok, folded = try_eval_const(ds[1].default, st.consts)
    if !ok
        message = String(folded)
        code = occursin("is not a constant", message) ? "E003" : "E001"
        _report!(
            b,
            st;
            code = code,
            message = "invalid $what of `$(st.path)`: " * message,
            scope = scope,
            hint = "a model-level value may use literals and the block's `@constants`",
        )
        return nothing
    end
    return folded
end

function _check_value(value, t::BGSim.TypeSpec, shape::Union{Tuple{Vararg{Int}},Nothing})
    shape === nothing && return (false, "the size is not static")
    isempty(shape) && return _check_scalar_value(value, BGSim.type_kind(t))
    length(shape) == 1 && return _check_vector_value(value, shape[1])
    return _check_matrix_value(value, shape[1], shape[2])
end

function _check_scalar_value(value, kind::Symbol)
    kind === :Real &&
        return (value isa Real && !(value isa Bool), "expected a Real value")
    kind === :Int && return (value isa Integer && !(value isa Bool), "expected an Int value")
    kind === :Bool && return (value isa Bool, "expected a Bool value")
    return (false, "expected a scalar value")
end

function _check_vector_value(value, n::Int)
    value isa AbstractVector || return (false, "expected a vector of $n values")
    length(value) == n || return (false, "expected $n values, got $(length(value))")
    for v in value
        v isa Real && !(v isa Bool) || return (false, "the elements must be Real values")
    end
    return (true, "")
end

function _check_matrix_value(value, n::Int, m::Int)
    if value isa AbstractMatrix
        size(value) == (n, m) ||
            return (false, "expected a $n x $m matrix, got $(size(value, 1)) x $(size(value, 2))")
        return (true, "")
    end
    if value isa AbstractVector && length(value) == n &&
       all(r -> r isa AbstractVector && length(r) == m, value)
        return (true, "")
    end
    return (false, "expected a $n x $m matrix")
end

# ---------------------------------------------------------------------------------------
# Equation flattening
# ---------------------------------------------------------------------------------------

"""    _ddt_targets(pb) -> Set{Symbol}

The declared variables that appear as `ddt(x)` in the block: those are the states of the
instance's signal list (a variable that no equation differentiates is algebraic)."""
function _ddt_targets(pb::BGSim.ParsedBlock)
    out = Set{Symbol}()
    for item in BGSim.equations(pb)
        _walk_ddt!(item, out)
    end
    return out
end

_walk_ddt!(e, out) = nothing

function _walk_ddt!(eq::Equation, out)
    _walk_expr_ddt!(eq.lhs, out)
    _walk_expr_ddt!(eq.rhs, out)
    return nothing
end

function _walk_ddt!(item::IfEquation, out)
    for branch in item.branches, sub in branch.body
        _walk_ddt!(sub, out)
    end
    return nothing
end

function _walk_ddt!(item::ForEquation, out)
    for sub in item.body
        _walk_ddt!(sub, out)
    end
    return nothing
end

_walk_expr_ddt!(e, out) = nothing

function _walk_expr_ddt!(e::Call, out)
    if e.fn.name === :ddt && length(e.args) == 1 && e.args[1] isa Name
        push!(out, e.args[1].name)
    end
    for a in e.args
        _walk_expr_ddt!(a, out)
    end
    return nothing
end

function _walk_expr_ddt!(e::BinOp, out)
    _walk_expr_ddt!(e.lhs, out)
    _walk_expr_ddt!(e.rhs, out)
    return nothing
end

function _walk_expr_ddt!(e::UnOp, out)
    _walk_expr_ddt!(e.operand, out)
    return nothing
end

function _walk_expr_ddt!(e::IfElse, out)
    _walk_expr_ddt!(e.cond, out)
    _walk_expr_ddt!(e.then, out)
    _walk_expr_ddt!(e.otherwise, out)
    return nothing
end

function _walk_expr_ddt!(e::Index, out)
    _walk_expr_ddt!(e.base, out)
    for i in e.indices
        _walk_expr_ddt!(i, out)
    end
    return nothing
end

function _walk_expr_ddt!(e::VectorLit, out)
    for x in e.elements
        _walk_expr_ddt!(x, out)
    end
    return nothing
end

function _walk_expr_ddt!(e::MatrixLit, out)
    for row in e.rows, x in row
        _walk_expr_ddt!(x, out)
    end
    return nothing
end

function _walk_expr_ddt!(e::Comparison, out)
    _walk_expr_ddt!(e.lhs, out)
    _walk_expr_ddt!(e.rhs, out)
    return nothing
end

function _walk_expr_ddt!(e::BoolOp, out)
    for x in e.operands
        _walk_expr_ddt!(x, out)
    end
    return nothing
end

function _walk_expr_ddt!(e::Field, out)
    _walk_expr_ddt!(e.base, out)
    return nothing
end

# ---------------------------------------------------------------------------------------
# QValue: a scalar or array expression while flattening
# ---------------------------------------------------------------------------------------

"""    QValue(shape, elems)

A qualified expression during flattening: `shape` is `()` for a scalar, `(n,)` for a vector
and `(n,m)` for a matrix; `elems` holds the scalar ASTs in row-major order. Scalarizing at
qualification time is what makes the flat model static (plan 2.1 principle 5) and lets the
lowering create one MTK variable per element."""
struct QValue
    shape::Tuple{Vararg{Int}}
    elems::Vector{BGSim.Expr}
end

_qscalar(e::BGSim.Expr) = QValue((), BGSim.Expr[e])

_qlen(q::QValue) = length(q.elems)

function _qpick(q::QValue, i::Int, j::Int = 1)
    return q.elems[_shape_element(q.shape, i, j)]
end

_qsame_shape(a::QValue, b::QValue) = a.shape == b.shape

"""
    _qarray_arg(q, range) -> Expr

One qualified argument as a single AST node again: the scalar itself, a `VectorLit` for a
vector, or a `MatrixLit` for a matrix. The D12 table intrinsics (`interp1`, `interp2`) are
the one place where an array argument stays whole instead of being unrolled to scalars.
"""
function _qarray_arg(q::QValue, r::BGSim.SourceRange)
    isempty(q.shape) && return q.elems[1]
    if length(q.shape) == 1
        return VectorLit(copy(q.elems), r)
    end
    n, m = q.shape
    rows = [BGSim.Expr[q.elems[(i - 1) * m + j] for j in 1:m] for i in 1:n]
    return MatrixLit(rows, r)
end

function _qmap1(q::QValue, f)
    return QValue(q.shape, BGSim.Expr[f(e) for e in q.elems])
end

function _qmap2(a::QValue, b::QValue, f)
    if a.shape == b.shape
        return QValue(a.shape, BGSim.Expr[f(x, y) for (x, y) in zip(a.elems, b.elems)])
    elseif isempty(a.shape)
        return QValue(b.shape, BGSim.Expr[f(a.elems[1], y) for y in b.elems])
    elseif isempty(b.shape)
        return QValue(a.shape, BGSim.Expr[f(x, b.elems[1]) for x in a.elems])
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Qualification
# ---------------------------------------------------------------------------------------

"""    QCtx(builder, state, locals)

The context of one expression: the instance, plus the loop variables bound by a `for`
unroll (plan 4.3: `for` is unrolled at instantiation)."""
struct QCtx
    b::Builder
    st::BlockState
    locals::Dict{Symbol,QValue}
end

_qreport!(q::QCtx; kwargs...) = _report!(q.b, q.st; kwargs...)

function _qualify(q::QCtx, e::BGSim.Expr)::Union{QValue,Nothing}
    return _qualify_node(q, e)
end

_qualify(q::QCtx, ::Nothing) = nothing

function _qualify_node(q::QCtx, e::Lit)
    return _qscalar(e)
end

function _qualify_node(q::QCtx, e::Name)
    name = e.name
    haskey(q.locals, name) && return q.locals[name]
    if name === :t
        return _qscalar(e)
    end
    if haskey(q.st.consts, name)
        return _const_qvalue(q, q.st.consts[name], BGSim.expr_range(e))
    end
    d = get(q.st.decls, name, nothing)
    if d === nothing
        _qreport!(
            q;
            code = "E003",
            message = "`$name` is used but not declared",
            range = BGSim.expr_range(e),
            hint = "declare it in @parameters, @variables, @inputs or @outputs",
        )
        return nothing
    end
    if BGSim.decl_scope(d) == :ports
        _qreport!(
            q;
            code = "E003",
            message = "`$name` is a power port; use `$name.e` or `$name.f`",
            range = BGSim.expr_range(e),
            hint = "a power port carries two variables, effort and flow",
        )
        return nothing
    end
    ids = get(q.st.ids, name, nothing)
    ids === nothing && return nothing   # a parameter whose value failed to bind; E-code already reported
    shape = q.st.shapes[name]
    r = BGSim.expr_range(e)
    return QValue(shape, BGSim.Expr[Name(Symbol(id), r) for id in ids])
end

function _const_qvalue(q::QCtx, value, r)
    if value isa Bool || value isa Real || value isa AbstractString
        return _qscalar(Lit(value, r))
    elseif value isa AbstractVector && all(v -> v isa Real, value)
        return QValue((length(value),), BGSim.Expr[Lit(v, r) for v in value])
    elseif value isa AbstractMatrix
        n, m = size(value)
        return QValue((n, m), BGSim.Expr[Lit(value[i, j], r) for i in 1:n for j in 1:m])
    elseif value isa AbstractVector && all(v -> v isa AbstractVector, value)
        n = length(value)
        m = n == 0 ? 0 : length(value[1])
        return QValue((n, m), BGSim.Expr[Lit(value[i][j], r) for i in 1:n for j in 1:m])
    end
    _qreport!(
        q;
        code = "E004",
        message = "constant value of type $(typeof(value)) cannot be used in an expression",
        range = r,
    )
    return nothing
end

function _qualify_node(q::QCtx, e::Field)
    base = e.base
    if !(base isa Name)
        _qreport!(
            q;
            code = "E003",
            message = "only a power port has fields `e` and `f`",
            range = BGSim.expr_range(e),
        )
        return nothing
    end
    port = get(q.st.ports, base.name, nothing)
    if port === nothing
        _qreport!(
            q;
            code = "E003",
            message = "`$(base.name)` is not a power port of `$(q.st.path)`",
            range = BGSim.expr_range(e),
            hint = "fields `e` and `f` exist only on `@ports`",
        )
        return nothing
    end
    field = e.field
    if field !== :e && field !== :f
        _qreport!(
            q;
            code = "E003",
            message = "a power port has fields `e` and `f`, not `$field`",
            range = BGSim.expr_range(e),
        )
        return nothing
    end
    ids = field === :e ? port.eids : port.fids
    r = BGSim.expr_range(e)
    if port.size == 1
        return _qscalar(Field(Name(Symbol(port.qname), r), field, r))
    end
    return QValue((port.size,), BGSim.Expr[Name(Symbol(id), r) for id in ids])
end

function _qualify_node(q::QCtx, e::Index)
    base = _qualify(q, e.base)
    base === nothing && return nothing
    indices = Int[]
    for idx in e.indices
        value = _fold_index(q, idx)
        if value === nothing
            _qreport!(
                q;
                code = "E005",
                message = "an index must be a static integer after `for` unrolling",
                range = BGSim.expr_range(idx),
                hint = "use a literal index or a `for` loop variable",
            )
            return nothing
        end
        push!(indices, value)
    end
    shape = base.shape
    if isempty(shape)
        _qreport!(
            q;
            code = "E005",
            message = "`$(sprint(show, e.base))` is a scalar and cannot be indexed",
            range = BGSim.expr_range(e),
        )
        return nothing
    end
    if length(shape) != length(indices)
        _qreport!(
            q;
            code = "E005",
            message = "an array of size $(shape) takes $(length(shape)) indices, got $(length(indices))",
            range = BGSim.expr_range(e),
        )
        return nothing
    end
    for (k, i) in enumerate(indices)
        (1 <= i <= shape[k]) || begin
            _qreport!(
                q;
                code = "E005",
                message = "index $i is out of range for size $(shape)",
                range = BGSim.expr_range(e),
                hint = "use an index between 1 and $(shape[k])",
            )
            return nothing
        end
    end
    if length(indices) == 1
        return _qscalar(_qpick(base, indices[1]))
    end
    return _qscalar(_qpick(base, indices[1], indices[2]))
end

function _fold_index(q::QCtx, e::BGSim.Expr)
    v = _qualify(q, e)
    v === nothing && return nothing
    isempty(v.shape) || return nothing
    ok, value = try_eval_const(v.elems[1], q.st.consts)
    ok || return nothing
    return value isa Integer ? Int(value) : nothing
end

function _qualify_node(q::QCtx, e::VectorLit)
    parts = QValue[]
    for el in e.elements
        v = _qualify(q, el)
        v === nothing && return nothing
        isempty(v.shape) || begin
            _qreport!(
                q;
                code = "E004",
                message = "a vector literal cannot contain an array",
                range = BGSim.expr_range(el),
            )
            return nothing
        end
        push!(parts, v)
    end
    return QValue((length(parts),), BGSim.Expr[p.elems[1] for p in parts])
end

function _qualify_node(q::QCtx, e::MatrixLit)
    rows = Vector{Vector{BGSim.Expr}}()
    for row in e.rows
        exprs = BGSim.Expr[]
        for el in row
            v = _qualify(q, el)
            v === nothing && return nothing
            isempty(v.shape) || begin
                _qreport!(
                    q;
                    code = "E004",
                    message = "a matrix literal cannot contain an array",
                    range = BGSim.expr_range(el),
                )
                return nothing
            end
            push!(exprs, v.elems[1])
        end
        push!(rows, exprs)
    end
    n = length(rows)
    m = n == 0 ? 0 : length(rows[1])
    for row in rows
        length(row) == m || begin
            _qreport!(
                q;
                code = "E004",
                message = "matrix literal rows must all have the same length",
                range = BGSim.expr_range(e),
            )
            return nothing
        end
    end
    return QValue((n, m), BGSim.Expr[rows[i][j] for i in 1:n for j in 1:m])
end

function _qualify_node(q::QCtx, e::IfElse)
    cond = _qualify(q, e.cond)
    then = _qualify(q, e.then)
    otherwise = _qualify(q, e.otherwise)
    (cond === nothing || then === nothing || otherwise === nothing) && return nothing
    isempty(cond.shape) || begin
        _qreport!(
            q;
            code = "E004",
            message = "the condition of `ifelse` must be a scalar",
            range = BGSim.expr_range(e.cond),
        )
        return nothing
    end
    r = BGSim.expr_range(e)
    c = cond.elems[1]
    out = _qmap2(then, otherwise, (a, b) -> IfElse(c, a, b, r))
    out === nothing && _qreport!(
        q;
        code = "E004",
        message = "the branches of `ifelse` must have the same size",
        range = r,
    )
    return out
end

function _qualify_node(q::QCtx, e::Comparison)
    lhs = _qualify(q, e.lhs)
    rhs = _qualify(q, e.rhs)
    (lhs === nothing || rhs === nothing) && return nothing
    (isempty(lhs.shape) && isempty(rhs.shape)) || begin
        _qreport!(
            q;
            code = "E004",
            message = "a comparison needs scalar operands",
            range = BGSim.expr_range(e),
        )
        return nothing
    end
    return _qscalar(Comparison(e.op, lhs.elems[1], rhs.elems[1], BGSim.expr_range(e)))
end

function _qualify_node(q::QCtx, e::BoolOp)
    parts = BGSim.Expr[]
    for operand in e.operands
        v = _qualify(q, operand)
        v === nothing && return nothing
        isempty(v.shape) || begin
            _qreport!(
                q;
                code = "E004",
                message = "a logical operator needs scalar operands",
                range = BGSim.expr_range(e),
            )
            return nothing
        end
        push!(parts, v.elems[1])
    end
    return _qscalar(BoolOp(e.op, parts, BGSim.expr_range(e)))
end

function _qualify_node(q::QCtx, e::UnOp)
    operand = _qualify(q, e.operand)
    operand === nothing && return nothing
    r = BGSim.expr_range(e)
    if e.op === :! || e.op === Symbol("!")
        isempty(operand.shape) || begin
            _qreport!(
                q;
                code = "E004",
                message = "`!` needs a scalar",
                range = r,
            )
            return nothing
        end
        return _qscalar(UnOp(e.op, operand.elems[1], r))
    end
    return _qmap1(operand, x -> UnOp(e.op, x, r))
end

function _qualify_node(q::QCtx, e::BinOp)
    lhs = _qualify(q, e.lhs)
    rhs = _qualify(q, e.rhs)
    (lhs === nothing || rhs === nothing) && return nothing
    r = BGSim.expr_range(e)
    op = e.op
    if op === :+ || op === :-
        out = _qmap2(lhs, rhs, (a, b) -> BinOp(op, a, b, r))
        out === nothing && _qreport!(
            q;
            code = "E004",
            message = "cannot $(op === :+ ? "add" : "subtract") arrays of different sizes $(lhs.shape) and $(rhs.shape)",
            range = r,
        )
        return out
    elseif op === :*
        if isempty(lhs.shape) && isempty(rhs.shape)
            return _qscalar(BinOp(op, lhs.elems[1], rhs.elems[1], r))
        elseif isempty(lhs.shape)
            return _qmap1(rhs, y -> BinOp(op, lhs.elems[1], y, r))
        elseif isempty(rhs.shape)
            return _qmap1(lhs, x -> BinOp(op, x, rhs.elems[1], r))
        elseif length(lhs.shape) == 2 && length(rhs.shape) == 1
            # `A * x`, the matrix-vector product the spec's function table lists next to
            # `transpose` and `A \ b`. One scalar equation per row: `sum_j A[i,j]*x[j]`.
            n, m = lhs.shape
            if m != rhs.shape[1]
                _qreport!(
                    q;
                    code = "E004",
                    message = "a matrix-vector product needs a $(n)x$(m) matrix and a $m-vector, got $(lhs.shape) and $(rhs.shape)",
                    range = r,
                )
                return nothing
            end
            elems = BGSim.Expr[]
            for i in 1:n
                terms = BGSim.Expr[
                    BinOp(:*, _qpick(lhs, i, j), rhs.elems[j], r) for j in 1:m
                ]
                push!(elems, _sum_exprs(terms, r))
            end
            return QValue((n,), elems)
        end
        _qreport!(
            q;
            code = "E004",
            message = "element-wise multiplication of two arrays is not defined; use `dot` or scale by a scalar",
            range = r,
        )
        return nothing
    elseif op === :/
        if isempty(lhs.shape) && isempty(rhs.shape)
            return _qscalar(BinOp(op, lhs.elems[1], rhs.elems[1], r))
        elseif isempty(rhs.shape)
            return _qmap1(lhs, x -> BinOp(op, x, rhs.elems[1], r))
        elseif isempty(lhs.shape)
            return _qmap1(rhs, y -> BinOp(op, lhs.elems[1], y, r))
        end
        _qreport!(
            q;
            code = "E004",
            message = "element-wise division of two arrays is not defined; divide by a scalar",
            range = r,
        )
        return nothing
    elseif op === Symbol("\\")
        if isempty(lhs.shape) && isempty(rhs.shape)
            return _qscalar(BinOp(op, lhs.elems[1], rhs.elems[1], r))
        end
        _qreport!(
            q;
            code = "E004",
            message = "the `\\` operator needs scalar operands",
            range = r,
        )
        return nothing
    elseif op === :^
        isempty(rhs.shape) || begin
            _qreport!(
                q;
                code = "E004",
                message = "the exponent must be a scalar",
                range = r,
            )
            return nothing
        end
        return _qmap1(lhs, x -> BinOp(op, x, rhs.elems[1], r))
    end
    if isempty(lhs.shape) && isempty(rhs.shape)
        return _qscalar(BinOp(op, lhs.elems[1], rhs.elems[1], r))
    end
    _qreport!(
        q;
        code = "E004",
        message = "operator `$op` needs scalar operands",
        range = r,
    )
    return nothing
end

function _qualify_node(q::QCtx, e::Call)
    fn = e.fn.name
    r = BGSim.expr_range(e)
    args = QValue[]
    for a in e.args
        v = _qualify(q, a)
        v === nothing && return nothing
        push!(args, v)
    end
    # ddt / int are element-wise over an array argument (the lowering expands them too).
    if fn === :ddt && length(args) == 1
        a = args[1]
        return _qmap1(a, x -> Call(Name(fn, e.fn.range), BGSim.Expr[x], r))
    elseif fn === :int && length(args) == 2
        a, b = args[1], args[2]
        if isempty(b.shape)
            return _qmap1(a, x -> Call(Name(fn, e.fn.range), BGSim.Expr[x, b.elems[1]], r))
        end
        out = _qmap2(a, b, (x, y) -> Call(Name(fn, e.fn.range), BGSim.Expr[x, y], r))
        out === nothing && _qreport!(
            q;
            code = "E004",
            message = "`int` needs a scalar or matching start value",
            range = r,
        )
        return out
    elseif fn === :interp1 || fn === :interp2
        # The D12 table intrinsics take the table as array arguments: keep the whole Vec/Mat
        # instead of lifting the call element-wise (which would make one 1-point lookup per
        # table entry). `lower_call` registers them as opaque functions.
        return _qscalar(
            Call(Name(fn, e.fn.range), BGSim.Expr[_qarray_arg(a, r) for a in args], r)
        )
    elseif fn === :ifelse || fn === :max || fn === :min || fn === :clamp ||
           fn === :abs || fn === :sign || fn === :sqrt || fn === :exp ||
           fn === :log || fn === :log10 || fn === :sin || fn === :cos ||
           fn === :tan || fn === :asin || fn === :acos || fn === :atan ||
           fn === :sinh || fn === :cosh || fn === :tanh || fn === :floor ||
           fn === :ceil || fn === :round || fn === :hypot || fn === :mod ||
           fn === :rem || fn === :deadzone || fn === :saturate ||
           fn === :previous || fn === :hold || fn === :delay ||
           fn === :noise_normal || fn === :reinit
        # A scalar function: every argument must be scalar. `min`/`max`/`clamp`/`abs` also
        # work on the same-shaped arrays in the language, so lift them element-wise when all
        # arguments have one common array shape.
        if any(a -> !isempty(a.shape), args)
            shapes = unique(a.shape for a in args if !isempty(a.shape))
            if length(shapes) == 1
                shape = shapes[1]
                all(a -> isempty(a.shape) || a.shape == shape, args) || begin
                    _qreport!(
                        q;
                        code = "E004",
                        message = "`$fn` arguments must have one size",
                        range = r,
                    )
                    return nothing
                end
                elems = BGSim.Expr[]
                for k in 1:_shape_length(shape)
                    call_args = BGSim.Expr[
                        isempty(a.shape) ? a.elems[1] : a.elems[k] for a in args
                    ]
                    push!(elems, Call(Name(fn, e.fn.range), call_args, r))
                end
                return QValue(shape, elems)
            end
            _qreport!(
                q;
                code = "E004",
                message = "`$fn` needs scalar arguments",
                range = r,
            )
            return nothing
        end
        return _qscalar(Call(Name(fn, e.fn.range), BGSim.Expr[a.elems[1] for a in args], r))
    elseif fn === :dot && length(args) == 2
        a, b = args[1], args[2]
        if a.shape != b.shape || isempty(a.shape)
            _qreport!(
                q;
                code = "E004",
                message = "`dot` needs two vectors of the same length",
                range = r,
            )
            return nothing
        end
        terms = BGSim.Expr[BinOp(:*, a.elems[k], b.elems[k], r) for k in 1:length(a.elems)]
        return _qscalar(_sum_exprs(terms, r))
    elseif fn === :norm && length(args) == 1
        a = args[1]
        if isempty(a.shape)
            return _qscalar(Call(Name(:abs, e.fn.range), BGSim.Expr[a.elems[1]], r))
        end
        squares = BGSim.Expr[BinOp(:^, x, Lit(2, r), r) for x in a.elems]
        return _qscalar(Call(
            Name(:sqrt, e.fn.range),
            BGSim.Expr[_sum_exprs(squares, r)],
            r,
        ))
    elseif fn === :cross && length(args) == 2
        a, b = args[1], args[2]
        if a.shape != (3,) || b.shape != (3,)
            _qreport!(
                q;
                code = "E004",
                message = "`cross` needs two 3-vectors",
                range = r,
            )
            return nothing
        end
        elems = BGSim.Expr[
            BinOp(:-, BinOp(:*, a.elems[2], b.elems[3], r),
                BinOp(:*, a.elems[3], b.elems[2], r), r),
            BinOp(:-, BinOp(:*, a.elems[3], b.elems[1], r),
                BinOp(:*, a.elems[1], b.elems[3], r), r),
            BinOp(:-, BinOp(:*, a.elems[1], b.elems[2], r),
                BinOp(:*, a.elems[2], b.elems[1], r), r),
        ]
        return QValue((3,), elems)
    elseif fn === :transpose && length(args) == 1
        a = args[1]
        length(a.shape) == 2 || begin
            _qreport!(
                q;
                code = "E004",
                message = "`transpose` needs a matrix",
                range = r,
            )
            return nothing
        end
        n, m = a.shape
        return QValue((m, n), BGSim.Expr[a.elems[(i - 1) * m + j] for j in 1:m for i in 1:n])
    end
    # Unknown function: the block checker has already reported E002, so be silent here.
    if !isempty(args) && any(a -> !isempty(a.shape), args)
        _qreport!(
            q;
            code = "E004",
            message = "`$fn` needs scalar arguments",
            range = r,
        )
        return nothing
    end
    return _qscalar(Call(Name(fn, e.fn.range), BGSim.Expr[a.elems[1] for a in args], r))
end

# A left-associative sum; `isempty` is 0. Used for `dot`, `norm` and the junction sums.
function _sum_exprs(terms::Vector{BGSim.Expr}, r::BGSim.SourceRange)
    isempty(terms) && return Lit(0.0, r)
    out = terms[1]
    for t in terms[2:end]
        out = BinOp(:+, out, t, r)
    end
    return out
end

# ---------------------------------------------------------------------------------------
# Equation emission
# ---------------------------------------------------------------------------------------

function _emit_block_equations!(b::Builder, st::BlockState)
    for item in BGSim.equations(st.pb)
        _emit_item!(b, st, item, Dict{Symbol,QValue}())
    end
    return nothing
end

function _emit_item!(b::Builder, st::BlockState, item, locals::Dict{Symbol,QValue})
    if item isa Equation
        _emit_equation!(b, st, item, locals)
    elseif item isa ForEquation
        _emit_for!(b, st, item, locals)
    elseif item isa IfEquation
        _emit_if!(b, st, item, locals)
    end
    return nothing
end

function _emit_equation!(
    b::Builder,
    st::BlockState,
    eq::Equation,
    locals::Dict{Symbol,QValue},
)
    q = QCtx(b, st, locals)
    lhs = _qualify(q, eq.lhs)
    rhs = _qualify(q, eq.rhs)
    (lhs === nothing || rhs === nothing) && return nothing
    lhs, rhs = _broadcast_pair(q, lhs, rhs, BGSim.source_range(eq))
    (lhs === nothing || rhs === nothing) && return nothing
    for k in 1:_qlen(lhs)
        push!(
            b.equations,
            Flat.FlatEq(
                lhs.elems[k],
                rhs.elems[k],
                Flat.Origin(; path = st.path, block = st.ref, node = st.node,
                    range = BGSim.source_range(eq), kind = :block),
            ),
        )
    end
    st.eq_count += _qlen(lhs)
    return nothing
end

function _broadcast_pair(q::QCtx, lhs::QValue, rhs::QValue, r)
    if lhs.shape == rhs.shape
        return lhs, rhs
    elseif isempty(lhs.shape)
        return QValue(rhs.shape, BGSim.Expr[lhs.elems[1] for _ in rhs.elems]), rhs
    elseif isempty(rhs.shape)
        return lhs, QValue(lhs.shape, BGSim.Expr[rhs.elems[1] for _ in lhs.elems])
    end
    _qreport!(
        q;
        code = "E004",
        message = "cannot equate arrays of different sizes $(lhs.shape) and $(rhs.shape)",
        range = r,
    )
    return nothing, nothing
end

function _emit_for!(
    b::Builder,
    st::BlockState,
    item::ForEquation,
    locals::Dict{Symbol,QValue},
)
    ok_lo, lo = try_eval_const(item.lo, st.consts)
    ok_hi, hi = try_eval_const(item.hi, st.consts)
    step = 1
    if item.step !== nothing
        ok_step, s = try_eval_const(item.step, st.consts)
        (ok_step && s isa Integer) || begin
            _report!(
                b,
                st;
                code = "E005",
                message = "the step of `for $(item.var)` must be a constant integer",
                range = BGSim.source_range(item),
            )
            return nothing
        end
        step = Int(s)
    end
    if !(ok_lo && ok_hi && lo isa Integer && hi isa Integer && step != 0)
        _report!(
            b,
            st;
            code = "E005",
            message = "the bounds of `for $(item.var)` must be constant integers",
            range = BGSim.source_range(item),
            hint = "use literals or `@constants`; a size depending on a parameter is not static",
        )
        return nothing
    end
    values = collect(Int(lo):step:Int(hi))
    for i in values
        inner = copy(locals)
        inner[item.var] = _qscalar(Lit(i, BGSim.source_range(item)))
        for sub in item.body
            _emit_item!(b, st, sub, inner)
        end
    end
    return nothing
end

function _emit_if!(
    b::Builder,
    st::BlockState,
    item::IfEquation,
    locals::Dict{Symbol,QValue},
)
    isempty(item.branches) && return nothing
    n = length(item.branches[1].body)
    for branch in item.branches
        if length(branch.body) != n
            _report!(
                b,
                st;
                code = "E001",
                message = "every branch of an `if` must hold the same number of equations",
                range = BGSim.source_range(item),
                hint = "give each branch $n equations",
            )
            return nothing
        end
    end
    for k in 1:n
        rows = Tuple{BGSim.Expr,Union{BGSim.Expr,Nothing},QValue}[]
        for branch in item.branches
            sub = branch.body[k]
            if !(sub isa Equation)
                _report!(
                    b,
                    st;
                    code = "E001",
                    message = "an `if` around equations may only hold equations",
                    range = BGSim.source_range(sub),
                )
                return nothing
            end
            q = QCtx(b, st, locals)
            lhs = _qualify(q, sub.lhs)
            rhs = _qualify(q, sub.rhs)
            (lhs === nothing || rhs === nothing) && return nothing
            (isempty(lhs.shape) && isempty(rhs.shape)) || begin
                _qreport!(
                    q;
                    code = "E004",
                    message = "an `if` around equations needs scalar equations",
                    range = BGSim.source_range(sub),
                )
                return nothing
            end
            cond = nothing
            if branch.cond !== nothing
                c = _qualify(q, branch.cond)
                if c === nothing || !isempty(c.shape)
                    _report!(
                        b,
                        st;
                        code = "E004",
                        message = "the condition of an `if` must be a scalar",
                        range = BGSim.source_range(branch),
                    )
                    return nothing
                end
                cond = c.elems[1]
            end
            push!(rows, (lhs.elems[1], cond, rhs))
        end
        first_id = Flat.flat_id(rows[1][1])
        for row in rows[2:end]
            if Flat.flat_id(row[1]) != first_id
                _report!(
                    b,
                    st;
                    code = "E001",
                    message = "the branches of an `if` must have the same left-hand side",
                    range = BGSim.source_range(item),
                    hint = "all branches define `$(sprint(show, rows[1][1]))`; split unrelated equations out of the `if`",
                )
                return nothing
            end
        end
        # if c1 then rhs1 elseif c2 then rhs2 else rhsN, right-associated.
        rhs_expr = rows[end][3].elems[1]
        for idx in (length(rows) - 1):-1:1
            cond = rows[idx][2]
            if cond === nothing
                rhs_expr = rows[idx][3].elems[1]
            else
                rhs_expr = IfElse(
                    cond,
                    rows[idx][3].elems[1],
                    rhs_expr,
                    BGSim.source_range(item),
                )
            end
        end
        push!(
            b.equations,
            Flat.FlatEq(
                rows[1][1],
                rhs_expr,
                Flat.Origin(; path = st.path, block = st.ref, node = st.node,
                    range = BGSim.source_range(item), kind = :block),
            ),
        )
        st.eq_count += 1
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Textual composites (@components / @connections, J2.6, decision D5)
# ---------------------------------------------------------------------------------------

"""`(block, port) -> :power | :input | :output | nothing` for a declared interface port of a
resolved block. Used to derive the connection kind of a textual `connect(...)`."""
function _declared_port_kind(block::IR.BlockDef, name::Symbol)
    for scope in (:ports, :inputs, :outputs)
        for d in BGSim.declarations(block.ast, scope)
            BGSim.decl_name(d) == name || continue
            return scope === :ports ? :power : scope === :inputs ? :input : :output
        end
    end
    return nothing
end

"""The declared power domain of a port of a resolved block, or `nothing`."""
function _declared_port_domain(block::IR.BlockDef, name::Symbol)
    for d in BGSim.ports(block.ast)
        BGSim.decl_name(d) == name || continue
        t = BGSim.resolve_type(BGSim.decl_type(d), BGSim.constant_env(block.ast))
        return something(BGSim.type_domain(t), :Generic)
    end
    return nothing
end

"""
    _find_named_block(b, name) -> (matches, where)

Resolve a component's block by name: the project library shadows the stdlib, and a name
declared twice in the same namespace is ambiguous (E101). This is the only place a textual
composite names a block; everything after it uses the plan 3.1 ref (`stdlib:…`/`project:…`),
so the component is instantiated by exactly the same code as a model-JSON node.
"""
function _find_named_block(b::Builder, name::Symbol)
    groups = (
        ("project library", [v for v in values(_load_project!(b)) if v.name === name]),
        ("standard library", [v for v in values(_load_stdlib!(b)) if v.name === name]),
    )
    for (where, matches) in groups
        isempty(matches) && continue
        return matches, where
    end
    return IR.BlockDef[], ""
end

_repr_value(v::Bool) = v ? "true" : "false"
_repr_value(v::AbstractFloat) = repr(Float64(v))
_repr_value(v::Real) = string(v)
_repr_value(v::AbstractVector) = "[" * join((_repr_value(x) for x in v), ", ") * "]"
_repr_value(v::AbstractMatrix) =
    "[" * join(("[" * join((_repr_value(v[i, j]) for j in 1:size(v, 2)), ", ") * "]"
                for i in 1:size(v, 1)), ", ") * "]"
_repr_value(v) = string(v)

"""Report a composite-expansion problem with the component's instance path (plan 3.4)."""
function _report_component!(
    b::Builder,
    node::IR.ModelNode,
    path::String,
    ref::Union{String,Nothing};
    code,
    message,
    hint = nothing,
)
    push!(
        b.diagnostics,
        diag(
            code,
            message;
            hint = hint,
            path = path,
            block = ref,
            node = node.id,
        ),
    )
    return nothing
end

"""
    _bind_composite_parameters!(b, node, path, block)

Bind the `@parameters` of a textual composite at the composite's own path (`Motor1/R`), so a
model-level override and `set_parameter_values` keep working exactly as for a flat block. A
composite parameter that is itself aliased to an enclosing composite's parameter (nested
composites, J2.6b) is not created again: `param_alias` already points at the outer id.
"""
function _bind_composite_parameters!(b::Builder, node::IR.ModelNode, path::String,
    block::IR.BlockDef)
    pb = block.ast
    consts = BGSim.constant_env(pb)
    st = BlockState(
        path,
        node.id,
        block.ref,
        block,
        pb,
        consts,
        BGSim.Units.block_domain(pb),
        :Generic,
        Dict{Symbol,BGSim.Decl}(),
        Dict{Symbol,Vector{String}}(),
        Dict{Symbol,Tuple{Vararg{Int}}}(),
        Dict{Symbol,Union{Dims,Nothing}}(),
        Dict{Symbol,PortInfo}(),
        0,
        0,
    )
    for scope in (:constants, :parameters, :variables, :inputs, :outputs, :ports)
        for d in BGSim.declarations(pb, scope)
            st.decls[BGSim.decl_name(d)] = d
        end
    end
    # Apply the instance's `@constants` overrides exactly like a flat block, so a composite
    # parameter default may use them.
    _bind_constants!(b, st, node)
    consts = st.consts
    for d in BGSim.declarations(pb, :parameters)
        name = BGSim.decl_name(d)
        t = BGSim.resolve_type(BGSim.decl_type(d), consts)
        shape = _shape_of(t, consts)
        if shape === nothing
            _report!(
                b,
                st;
                code = "E005",
                message = "the size of parameter `$name` is not static",
                range = BGSim.decl_range(d),
                scope = "@parameters",
            )
            continue
        end
        alias = get(b.param_alias, (path, name), nothing)
        if alias !== nothing
            ids = _element_ids(alias, shape)
            if !all(haskey(b.param_index, id) for id in ids)
                _report!(
                    b,
                    st;
                    code = "E003",
                    message = "parameter `$name` of `$(path)` aliases unknown parameter `$alias`",
                    range = BGSim.decl_range(d),
                    scope = "@parameters",
                )
            end
            continue
        end
        text = get(node.params, String(name), nothing)
        value = if text !== nothing
            _parse_value(
                b,
                st,
                text,
                t,
                shape;
                what = "parameter `$name`",
                scope = "@parameters",
            )
        elseif BGSim.decl_default(d) !== nothing
            ok, folded = try_eval_const(BGSim.decl_default(d), consts)
            if ok
                folded
            else
                _report!(
                    b,
                    st;
                    code = "E001",
                    message = "the default of parameter `$name` is not a constant expression",
                    range = BGSim.decl_range(d),
                    scope = "@parameters",
                    hint = "write a literal or a `@constants` expression",
                )
                nothing
            end
        else
            _report!(
                b,
                st;
                code = "E004",
                message = "parameter `$name` of `$(path)` has no value",
                range = BGSim.decl_range(d),
                scope = "@parameters",
                hint = "give it a default in the composite, or set it on the instance",
            )
            nothing
        end
        value === nothing && continue
        ok, message = _check_value(value, t, shape)
        if !ok
            _report!(
                b,
                st;
                code = "E004",
                message = "invalid value for parameter `$name` of `$(path)`: $message",
                range = BGSim.decl_range(d),
                scope = "@parameters",
            )
            continue
        end
        ids = _element_ids(_qname(st, name), shape)
        unit = get(BGSim.Units.unit_env(pb).names, name, nothing)
        values = _scalar_values(value, shape)
        for (k, id) in enumerate(ids)
            _add_param!(
                b,
                Flat.FlatParam(
                    id,
                    String(name),
                    values[k],
                    BGSim.type_element(t),
                    unit,
                    copy(BGSim.decl_attrs(d)),
                    Flat.Origin(; path = path, block = block.ref, node = node.id,
                        range = BGSim.decl_range(d), kind = :parameter),
                ),
            )
        end
    end
    return st.consts
end

# Split an observation target into `(instance, port, variable, field)`. A port field is
# `Field(Field(Name(instance), port), field)`; a variable is `Field(Name(instance), variable)`.
function _obs_parts(e::BGSim.Field)
    if e.base isa BGSim.Field && e.base.base isa BGSim.Name
        return (e.base.base.name, e.base.field, nothing, e.field)
    elseif e.base isa BGSim.Name
        return (e.base.name, nothing, e.field, nothing)
    end
    return (nothing, nothing, nothing, nothing)
end
_obs_parts(::Any) = (nothing, nothing, nothing, nothing)

"""
    _bind_observations!(b, node, path, block)

Resolve the `@observables` of a textual composite after its components are instantiated. Each
entry becomes a [`Flat.DerivedSignal`](@ref) at the composite path, so the composite records
the same signal id the flat block did (`Motor1/i`, `Motor1/shaft.f`). A port `e`/`f` alias
also gets the derived power `port.P`, exactly like a real port. Observed signals are derived
(one equation each) and never add a state.
"""
function _bind_observations!(b::Builder, node::IR.ModelNode, path::String,
    block::IR.BlockDef)
    for o in BGSim.observations(block.ast)
        name = BGSim.observation_name(o)
        field = BGSim.observation_field(o)
        target = BGSim.observation_target(o)
        instance, port_name, var_name, target_field = _obs_parts(target)
        if instance === nothing
            _report_component!(
                b, node, path, block.ref;
                code = "E003",
                message = "observed signal `$name` needs an `instance.signal` target",
                hint = "write `i = inductor.i` or `p.e = resistor.p.e`",
            )
            continue
        end
        tpath = _join(path, instance)
        st = get(b.state_by_path, tpath, nothing)
        if st === nothing
            _report_component!(
                b, node, tpath, nothing;
                code = "E003",
                message = "observed signal `$name` refers to unknown component `$instance`",
                hint = "declare it in `@components`",
            )
            continue
        end
        if target_field === nothing
            d = get(st.decls, var_name, nothing)
            ids = get(st.ids, var_name, String[])
            if d === nothing || BGSim.decl_scope(d) != :variables || isempty(ids)
                _report_component!(
                    b, node, tpath, st.ref;
                    code = "E102",
                    message = "`$(st.path)` has no variable `$var_name` to observe",
                    hint = "observe a `@variables` quantity, or a port field `instance.port.e`",
                )
                continue
            end
            id = _join(path, String(name))
            v = var_by_id(b, ids[1])
            _add_observed!(
                b, node, path, block, Flat.DerivedSignal(
                    id, :observed, v === nothing ? nothing : v.unit, path,
                    BGSim.type_element(BGSim.decl_type(d)),
                    BGSim.Name(Symbol(ids[1]), BGSim.SourceRange("", 0, 0, 0, 0)),
                ),
            )
        else
            port = get(st.ports, port_name, nothing)
            if port === nothing
                _report_component!(
                    b, node, tpath, st.ref;
                    code = "E102",
                    message = "`$(st.path)` has no port `$port_name` to observe",
                    hint = "an observed port field names a `@ports` entry of the component",
                )
                continue
            end
            if port.size != 1
                _report_component!(
                    b, node, tpath, st.ref;
                    code = "E102",
                    message = "observed port `$port_name` of `$(st.path)` has $(port.size) components",
                    hint = "a composite observable aliases one scalar port",
                )
                continue
            end
            if target_field !== :e && target_field !== :f
                _report_component!(
                    b, node, tpath, st.ref;
                    code = "E102",
                    message = "a port has fields `e` and `f`, not `$target_field`",
                )
                continue
            end
            ids = target_field === :e ? port.eids : port.fids
            if isempty(ids)
                _report_component!(
                    b, node, tpath, st.ref;
                    code = "E102",
                    message = "port `$port_name` of `$(st.path)` has no `$target_field`",
                )
                continue
            end
            id = _join(path, String(name) * "." * String(field === nothing ? target_field : field))
            v = var_by_id(b, ids[1])
            _add_observed!(
                b, node, path, block, Flat.DerivedSignal(
                    id, :port, v === nothing ? nothing : v.unit, path, :Real,
                    BGSim.Name(Symbol(ids[1]), BGSim.SourceRange("", 0, 0, 0, 0)),
                ),
            )
            target_field === :e &&
                _add_observed_power!(b, node, path, block, String(name), port)
        end
    end
    return nothing
end

# Record one observed signal, refusing an id that already exists as a variable/parameter or
# as another observed entry.
function _add_observed!(b::Builder, node::IR.ModelNode, path::String,
    block::IR.BlockDef, d::Flat.DerivedSignal)
    if haskey(b.var_index, d.id) || haskey(b.param_index, d.id) ||
       any(o -> o.id == d.id, b.observed)
        _report_component!(
            b, node, path, block.ref;
            code = "E003",
            message = "observed signal `$(d.id)` already exists",
            hint = "choose another observed name",
        )
        return nothing
    end
    push!(b.observed, d)
    return nothing
end

# `port.P` for an observed port, derived from the component port's own e/f.
function _add_observed_power!(b::Builder, node::IR.ModelNode, path::String,
    block::IR.BlockDef, portname::String, port::PortInfo)
    id = _join(path, portname * ".P")
    e = BGSim.Field(BGSim.Name(Symbol(port.qname), port.range), :e, port.range)
    f = BGSim.Field(BGSim.Name(Symbol(port.qname), port.range), :f, port.range)
    _add_observed!(
        b, node, path, block, Flat.DerivedSignal(
            id, :power, BGSim.Units.parse_unit("W"), path, :Real,
            BGSim.BinOp(:*, e, f, port.range),
        ),
    )
    return nothing
end

"""
    _composite_diagram!(b, node, path, block) -> (diagram, faces)

Lower a textual composite into the *same* intermediate representation a model-JSON subsystem
has: a `ModelDiagram` of component nodes plus wire/bond/signal connections, and the exposed
`SubsystemPort` list that maps each interface port onto the internal component port it
exposes. `_instantiate_diagram!` then flattens it with the `<Instance>/<child>` prefix rule,
so the textual and the JSON form share one implementation and produce the same flat model.

The `connect(a, gear.a)` entries that mention an interface port are *not* emitted as
connections: they become the boundary map. Every other entry is an ordinary connection; its
kind follows the same rules as the editor's (plan D7): signal when a signal port is involved,
bond when a `Generic` power port is involved, wire otherwise.
"""
function _composite_diagram!(b::Builder, node::IR.ModelNode, path::String, block::IR.BlockDef,
    consts = BGSim.constant_env(block.ast))
    pb = block.ast
    comps = BGSim.components(pb)
    conns = BGSim.connections(pb)
    param_names = Set(BGSim.decl_name(d) for d in BGSim.declarations(pb, :parameters))
    diagram = IR.ModelDiagram(IR.ModelNode[], IR.ModelConnection[])

    named = Dict{Symbol,IR.BlockDef}()
    ids = Dict{Symbol,String}()
    for comp in comps
        name = BGSim.component_name(comp)
        matches, where = _find_named_block(b, BGSim.component_block(comp))
        if isempty(matches)
            _report_component!(
                b, node, _join(path, name), nothing;
                code = "E101",
                message = "unknown block `$(BGSim.component_block(comp))` on component `$name` of `$(node.name)`",
                hint = "add `library/$(BGSim.component_block(comp)).jl` to the project library, or use a standard library block",
            )
            continue
        elseif length(matches) > 1
            _report_component!(
                b, node, _join(path, name), nothing;
                code = "E101",
                message = "block name `$(BGSim.component_block(comp))` is ambiguous in the $where",
                hint = "rename one of the blocks; a textual component refers to a block by name",
            )
            continue
        end
        component = only(matches)
        named[name] = component
        id = String(block.name) * "/" * String(name)
        ids[name] = id
        params = Dict{String,String}()
        for (key, expr) in BGSim.component_kwargs(comp)
            _declared_parameter(component, key) || _report_component!(
                b, node, _join(path, name), component.ref;
                code = "E003",
                message = "`$(component.name)` has no parameter `$key`",
                hint = "the keyword names a `@parameters` entry of the component block",
            )
            if expr isa BGSim.Name && expr.name in param_names
                # `key = composite_parameter`: a symbolic alias, not a folded constant. The
                # component's parameter ids become the composite's parameter ids, so a
                # model-level override and `set_parameter_values("Motor1/R")` stay live.
                target = get(b.param_alias, (path, expr.name), _join(path, expr.name))
                b.param_alias[(_join(path, name), key)] = target
                continue
            end
            ok, value = try_eval_const(expr, consts)
            if !ok
                message = String(value)
                _report_component!(
                    b, node, _join(path, name), component.ref;
                    code = occursin("is not a constant", message) ? "E003" : "E001",
                    message = "parameter `$key` of component `$name` is not a constant expression: $message",
                    hint = "a component parameter is bound when the composite is flattened, or aliases one of the composite's parameters",
                )
                continue
            end
            params[String(key)] = _repr_value(value)
        end
        push!(
            diagram.nodes,
            IR.ModelNode(
                id,
                String(name),
                :ref,
                component.ref,
                nothing,
                nothing,
                nothing,
                IR.SubsystemPort[],
                params,
                Dict{String,Any}(),
                Dict{String,String}(),
                nothing,
            ),
        )
    end

    faces = IR.SubsystemPort[]
    partner = Dict{Symbol,BGSim.PortRef}()
    for c in conns
        for (ref, other) in ((BGSim.connect_from(c), BGSim.connect_to(c)),
                             (BGSim.connect_to(c), BGSim.connect_from(c)))
            BGSim.portref_instance(ref) === nothing || continue
            name = BGSim.portref_port(ref)
            haskey(partner, name) && continue
            partner[name] = other
        end
    end

    # The interface: every `@ports` / `@inputs` / `@outputs` entry becomes one face.
    for (scope, kind, direction) in (
        (:ports, :power, nothing),
        (:inputs, :signal, :input),
        (:outputs, :signal, :output),
    )
        for d in BGSim.declarations(pb, scope)
            name = BGSim.decl_name(d)
            target = get(partner, name, nothing)
            if target === nothing || BGSim.portref_instance(target) === nothing
                _report_component!(
                    b, node, path, block.ref;
                    code = "E003",
                    message = "`$name` of the composite `$(node.name)` is not connected to a component port",
                    hint = "each interface port exposes exactly one internal port",
                )
                continue
            end
            instance = BGSim.portref_instance(target)
            component = get(named, instance, nothing)
            if component === nothing
                continue    # the component was reported above
            end
            target_port = BGSim.portref_port(target)
            if _declared_port_kind(component, target_port) === nothing
                _report_component!(
                    b, node, _join(path, instance), component.ref;
                    code = "E102",
                    message = "`$(component.name)` has no port `$target_port`",
                    hint = "an interface port exposes a `@ports`, `@inputs` or `@outputs` entry of the component",
                )
                continue
            end
            t = BGSim.resolve_type(BGSim.decl_type(d), consts)
            domain = kind === :power ? something(BGSim.type_domain(t), :Generic) : nothing
            if kind === :power
                target_domain = _declared_port_domain(component, target_port)
                if domain != :Generic && target_domain != :Generic &&
                   domain != target_domain
                    _report_component!(
                        b, node, _join(path, instance), component.ref;
                        code = "E102",
                        message = "interface port `$name` declares $(domain) but `$(component.name).$target_port` is $(target_domain)",
                        hint = "a composite port has the domain of the component port it exposes",
                    )
                    continue
                end
            end
            push!(
                faces,
                IR.SubsystemPort(
                    name,
                    kind,
                    direction,
                    domain,
                    :Real,
                    kind === :power ? Int[] : something(BGSim.type_size(t, consts), Int[]),
                    get(BGSim.decl_attrs(d), :unit, nothing),
                    get(BGSim.decl_attrs(d), :frame, nothing),
                    nothing,        # effortUnits
                    nothing,        # flowUnits
                    get(ids, instance, ""),
                    BGSim.portref_port(target),
                ),
            )
        end
    end

    # The wiring between components (interface-to-component entries are the faces above).
    for (k, c) in enumerate(conns)
        from = BGSim.connect_from(c)
        to = BGSim.connect_to(c)
        (BGSim.portref_instance(from) === nothing) && continue
        (BGSim.portref_instance(to) === nothing) && continue
        kind = _text_connection_kind!(
            b, node, path, named, BGSim.connect_from(c), BGSim.connect_to(c),
        )
        kind === nothing && continue
        f = IR.ModelEndpoint(get(ids, BGSim.portref_instance(from), ""), BGSim.portref_port(from))
        t = IR.ModelEndpoint(get(ids, BGSim.portref_instance(to), ""), BGSim.portref_port(to))
        if kind == :signal && _declared_port_kind(
            named[BGSim.portref_instance(from)], BGSim.portref_port(from),
        ) == :input
            f, t = t, f
        end
        push!(
            diagram.connections,
            IR.ModelConnection(
                _join(_join(path, String(block.name)), "c" * string(k)),
                kind,
                f,
                t,
                nothing,
            ),
        )
    end
    return diagram, faces
end

"""Whether a resolved block declares `name` in `@parameters`."""
function _declared_parameter(block::IR.BlockDef, name::Symbol)
    return any(
        d -> BGSim.decl_name(d) == name, BGSim.declarations(block.ast, :parameters)
    )
end

"""
The plan D7 kind of one textual `connect`: a signal when either side is a signal port (from
output to input), a bond when either power port is `Generic`, a wire for two concrete power
ports. Missing ports are E102 on the component, which is the same code and shape the
model-JSON flattener reports.
"""
function _text_connection_kind!(b, node, path, named, from, to)
    fi = BGSim.portref_instance(from)
    ti = BGSim.portref_instance(to)
    fp = BGSim.portref_port(from)
    tp = BGSim.portref_port(to)
    fb = get(named, fi, nothing)
    tb = get(named, ti, nothing)
    (fb === nothing || tb === nothing) && return nothing
    kf = _declared_port_kind(fb, fp)
    kt = _declared_port_kind(tb, tp)
    bad = kf === nothing ? (fi, fb, fp) : (kt === nothing ? (ti, tb, tp) : nothing)
    if bad !== nothing
        instance, component, port = bad
        _report_component!(
            b, node, _join(path, String(instance)), component.ref;
            code = "E102",
            message = "`$(component.name)` has no port `$port`",
            hint = "a `connect` names a `@ports`, `@inputs` or `@outputs` entry of the component",
        )
        return nothing
    end
    if kf in (:input, :output) || kt in (:input, :output)
        return :signal
    end
    df = _declared_port_domain(fb, fp)
    dt = _declared_port_domain(tb, tp)
    return (df === :Generic || dt === :Generic) ? :bond : :wire
end

"""Expand one textual composite at `path`: instantiate its synthetic diagram (with the same
prefix rule a model-JSON subsystem uses) and register its boundary faces. The stack refuses a
composite that contains itself, which would otherwise recurse without bound."""
function _instantiate_composite!(
    b::Builder,
    node::IR.ModelNode,
    path::String,
    block::IR.BlockDef,
)
    if block.ref in b.composite_stack
        _report_component!(
            b, node, path, block.ref;
            code = "E101",
            message = "the textual composite `$(block.name)` contains itself",
            hint = "a composite cannot instantiate itself, directly or through another composite",
        )
        return nothing
    end
    push!(b.composite_stack, block.ref)
    try
        consts = _bind_composite_parameters!(b, node, path, block)
        diagram, faces = _composite_diagram!(b, node, path, block, consts)
        diagram === nothing && return nothing
        _instantiate_diagram!(b, diagram, path)
        _bind_observations!(b, node, path, block)
        pseudo = IR.ModelNode(
            node.id,
            node.name,
            :subsystem,
            nothing,
            nothing,
            nothing,
            diagram,
            faces,
            Dict{String,String}(),
            Dict{String,Any}(),
            Dict{String,String}(),
            node.position,
        )
        _bind_boundary!(b, pseudo, path)
    finally
        pop!(b.composite_stack)
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Diagram walking
# ---------------------------------------------------------------------------------------

function _instantiate_diagram!(
    b::Builder,
    diagram::IR.ModelDiagram,
    prefix::String,
)
    nodes = Dict{String,IR.ModelNode}(n.id => n for n in diagram.nodes)
    for node in diagram.nodes
        path = _join(prefix, node.name)
        if node.block_kind == :junction
            info = Flat.JunctionInfo(node.id, path, something(node.junction, 1), Flat.JunctionBond[])
            push!(b.junctions, info)
            b.junction_by_path[path] = length(b.junctions)
            b.nodes_total += 1
        elseif node.block_kind == :subsystem
            sub = node.subsystem
            sub === nothing && continue
            _instantiate_diagram!(b, sub, path)
            _bind_boundary!(b, node, path)
        else
            block = resolve_block(b, node, path)
            block === nothing && continue
            if isempty(BGSim.components(block.ast))
                _instantiate_block!(b, node, path, block)
            else
                _instantiate_composite!(b, node, path, block)
            end
        end
    end
    for conn in diagram.connections
        from = _resolve_endpoint(b, nodes, conn.from, prefix)
        to = _resolve_endpoint(b, nodes, conn.to, prefix)
        push!(b.raw, RawConnection(conn, from, to, prefix))
        b.conns_total += 1
    end
    return nothing
end

"""    _internal_frame_connected(b, path, start, from_frame, face_frame) -> Bool

Whether the exposed internal port `start` is connected, through the subsystem's own bonds and
wire groups, to a transform instance whose two ports declare `from_frame` and `face_frame`
(D-MB5: a `FixedTransform`/`JointTransform` is the only legal bridge). Connectivity is what
matters: an unconnected transform anywhere in the subsystem must not justify the face.
"""
function _internal_frame_connected(
    b::Builder,
    path::String,
    start::RawEndpoint,
    from_frame::String,
    face_frame::String,
)
    slot(ep::RawEndpoint) = ep.kind == :junction ? _junction_key(ep.path) : _portkey(ep)
    adjacency = Dict{Tuple{String,Symbol},Vector{Tuple{String,Symbol}}}()
    for connection in b.raw
        inside = connection.diagram == path || startswith(connection.diagram, path * "/")
        inside || continue
        connection.conn.kind in (:bond, :wire) || continue
        for (a, z) in ((connection.from, connection.to), (connection.to, connection.from))
            a.kind in (:power, :junction) || continue
            z.kind in (:power, :junction) || continue
            push!(get!(adjacency, slot(a), Tuple{String,Symbol}[]), slot(z))
        end
    end
    start_key = slot(start)
    reachable = Set{Tuple{String,Symbol}}([start_key])
    queue = Tuple{String,Symbol}[start_key]
    while !isempty(queue)
        key = popfirst!(queue)
        for other in get(adjacency, key, Tuple{String,Symbol}[])
            other in reachable && continue
            push!(reachable, other)
            push!(queue, other)
        end
    end
    prefix = path * "/"
    for key in reachable
        startswith(key[1], "junction:") && continue
        startswith(key[1], prefix) || continue
        st = get(b.state_by_path, key[1], nothing)
        st === nothing && continue
        frames = String[p.frame for p in values(st.ports) if p.frame !== nothing]
        from_frame in frames && face_frame in frames && return true
    end
    return false
end

"""Check the declared domain, size, component units and frame of a subsystem power port
against the internal port it exposes (D-MB4/D-MB5, C-MB1 invariant).

A subsystem port's frame is authoritative for the exposed port. It may differ from the
internal port's catalog frame only when an internal `FixedTransform`/`JointTransform`
bridges the two named frames; a direct difference is E007."""
function _check_subsystem_power_port!(
    b::Builder,
    node::IR.ModelNode,
    path::String,
    sp::IR.SubsystemPort,
    internal::RawEndpoint,
)
    port = get(b.port_at, _portkey(internal), nothing)
    port === nothing && return nothing
    # A concrete multibond override of a Generic internal port is not supported in v1: the
    # internal port's flat ids were created as one scalar effort/flow pair. Say so instead of
    # reporting the raw size mismatch.
    override_width = isempty(sp.size) ? 1 : prod(sp.size)
    if port.domain == :Generic &&
       (sp.domain in (:Planar, :Spatial) || override_width != 1)
        _report_node!(
            b,
            node,
            path,
            nothing;
            code = "E102",
            message = "subsystem port `$(sp.name)` of `$(node.name)` overrides a Generic internal port `$(sp.port)` with a $(override_width)-component port; a Generic override must stay scalar",
            hint = "give the internal block the multibond domain (Power{Planar}/Power{Spatial}) instead of Power{Generic}; only the scalar override is supported",
        )
        return nothing
    end
    if sp.domain !== nothing && port.domain != :Generic && sp.domain != port.domain
        _report_node!(
            b,
            node,
            path,
            nothing;
            code = "E102",
            message = "subsystem port `$(sp.name)` of `$(node.name)` declares domain `$(sp.domain)`, but the internal `$(sp.port)` it exposes is `$(port.domain)`",
            hint = "give the subsystem port the internal port's domain, or change the internal block",
        )
    end
    if !isempty(sp.size) && prod(sp.size) != port.size
        _report_node!(
            b,
            node,
            path,
            nothing;
            code = "E102",
            message = "subsystem port `$(sp.name)` of `$(node.name)` declares size $(sp.size), but the internal `$(sp.port)` has $(port.size) component(s)",
            hint = "a multibond power port exposes all of its domain's components",
        )
    end
    components = BGSim.Library.domain_components(something(sp.domain, port.domain))
    for (what, declared, expected) in (
        ("effort", sp.effort_units, components === nothing ? nothing : components.effort),
        ("flow", sp.flow_units, components === nothing ? nothing : components.flow),
    )
        declared === nothing && continue
        if expected !== nothing && declared != expected
            _report_node!(
                b,
                node,
                path,
                nothing;
                code = "E102",
                message = "subsystem port `$(sp.name)` of `$(node.name)` has $(what)Units $(declared), but the catalog domain's components are $(expected)",
                hint = "derive the per-component units from the port's domain, or match its components exactly",
            )
        elseif expected === nothing && !(length(declared) in (3, 6))
            _report_node!(
                b,
                node,
                path,
                nothing;
                code = "E102",
                message = "subsystem port `$(sp.name)` of `$(node.name)` has $(length(declared)) $(what)Units; a multibond array is exactly 3 (Planar) or 6 (Spatial)",
                hint = "give the subsystem port a concrete domain, or list 3 or 6 component units",
            )
        end
    end
    # Frames: the face is authoritative. Equality is by the unqualified frame name (a named
    # frame is shared across instances, e.g. `world`); only the reported values are
    # instance-qualified.
    sp.frame === nothing && return nothing
    port.frame === nothing && return nothing
    sp.frame == port.frame && return nothing
    _internal_frame_connected(b, path, internal, port.frame, sp.frame) && return nothing
    push!(
        b.diagnostics,
        diag(
            "E007",
            "frame mismatch: subsystem port `$(sp.name)` of `$(node.name)` is in frame `$(sp.frame)`, but the internal `$(sp.port)` it exposes is in frame `$(port.frame)`",
            hint = "insert a FixedTransform or JointTransform inside the subsystem, or declare the subsystem port's frame equal to the internal port's frame; a null frame unifies with either",
            path = path,
            node = node.id,
            related = [BGSim.Related(internal.path,
                "the exposed internal port is here, in frame `$(port.frame)`")],
        ),
    )
    return nothing
end

function _bind_boundary!(b::Builder, node::IR.ModelNode, path::String)
    sub = node.subsystem
    sub === nothing && return nothing
    local_nodes = Dict{String,IR.ModelNode}(n.id => n for n in sub.nodes)
    boundary = Dict{Symbol,RawEndpoint}()
    for sp in node.subsystem_ports
        internal = _resolve_internal_port(b, local_nodes, sp, path, node)
        internal === nothing && continue
        kind_ok = if sp.kind == :power
            internal.kind == :power
        elseif sp.direction == :input
            internal.kind == :input
        else
            internal.kind == :output
        end
        if !kind_ok
            _report_node!(
                b,
                node,
                path,
                nothing;
                code = "E102",
                message = "subsystem port `$(sp.name)` of `$(node.name)` does not match the internal `$(sp.port)` it exposes",
                hint = "a signal port exposes an input or output of that direction; a power port exposes a `@ports` entry",
            )
            continue
        end
        sp.kind == :power && _check_subsystem_power_port!(b, node, path, sp, internal)
        boundary[sp.name] = internal
        b.boundary_ports[(path, sp.name)] = sp
    end
    b.boundary[path] = boundary
    b.boundary_nodes[path] = node.id
    return nothing
end

function _resolve_internal_port(
    b::Builder,
    local_nodes::Dict{String,IR.ModelNode},
    sp::IR.SubsystemPort,
    path::String,
    node::IR.ModelNode,
)
    inner = get(local_nodes, sp.node, nothing)
    if inner === nothing
        _report_node!(
            b,
            node,
            path,
            nothing;
            code = "E102",
            message = "subsystem port `$(sp.name)` refers to unknown node `$(sp.node)`",
        )
        return nothing
    end
    inner_path = _join(path, inner.name)
    boundary = get(b.boundary, inner_path, nothing)
    if boundary !== nothing
        return get(boundary, sp.port, nothing)
    end
    if inner.block_kind == :subsystem
        return nothing
    elseif inner.block_kind == :junction
        return RawEndpoint(inner.id, inner_path, nothing, :junction)
    end
    st = get(b.state_by_path, inner_path, nothing)
    if st === nothing
        return RawEndpoint(inner.id, inner_path, sp.port, :unknown)
    end
    d = get(st.decls, sp.port, nothing)
    kind = d === nothing ? :unknown :
           BGSim.decl_scope(d) == :ports ? :power :
           BGSim.decl_scope(d) == :inputs ? :input :
           BGSim.decl_scope(d) == :outputs ? :output : :unknown
    return RawEndpoint(inner.id, inner_path, sp.port, kind)
end

function _resolve_endpoint(
    b::Builder,
    local_nodes::Dict{String,IR.ModelNode},
    ep::IR.ModelEndpoint,
    prefix::String,
)
    node = get(local_nodes, ep.node, nothing)
    if node === nothing
        return RawEndpoint(ep.node, "", ep.port, :unknown)
    end
    path = _join(prefix, node.name)
    if node.block_kind == :junction
        return RawEndpoint(node.id, path, nothing, :junction)
    end
    boundary = get(b.boundary, path, nothing)
    if boundary !== nothing
        # A JSON subsystem node or a textual composite (J2.6): its face resolves to the
        # internal instance port it exposes. The face tuple keeps the exposed port's frame
        # authoritative for connections outside the subsystem (D-MB5).
        ep.port === nothing && return RawEndpoint(node.id, path, nothing, :unknown)
        face = (path, Symbol(ep.port))
        internal = get(boundary, Symbol(ep.port),
            RawEndpoint(node.id, path, Symbol(ep.port), :unknown))
        return RawEndpoint(internal.node, internal.path, internal.port, internal.kind, face)
    elseif node.block_kind == :subsystem
        ep.port === nothing && return RawEndpoint(node.id, path, nothing, :unknown)
        return RawEndpoint(node.id, path, Symbol(ep.port), :unknown)
    end
    st = get(b.state_by_path, path, nothing)
    if ep.port === nothing || st === nothing
        return RawEndpoint(node.id, path, ep.port, :unknown)
    end
    name = Symbol(ep.port)
    d = get(st.decls, name, nothing)
    kind = d === nothing ? :unknown :
           BGSim.decl_scope(d) == :ports ? :power :
           BGSim.decl_scope(d) == :inputs ? :input :
           BGSim.decl_scope(d) == :outputs ? :output : :unknown
    return RawEndpoint(node.id, path, name, kind)
end

# ---------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------

function instantiate!(b::Builder)
    _instantiate_diagram!(b, b.md.diagram, "")
    return b
end
