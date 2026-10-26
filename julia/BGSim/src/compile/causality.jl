# Causality (plan 5.7): the sequential causality assignment procedure (SCAP) on the bond
# graph, the causal strokes the editor draws, and the W201/W202/E106 diagnostics.
#
# The pass runs on the bond graph the flattening pipeline built (`junctions.jl`,
# `connect.jl`): every valid `:bond` connection is one bond, and each of its two ends is
# either a junction or a power port. A bond's causal stroke sits at the end where **effort is
# the input** to the element there (plan 5.7), so a bond always has exactly one stroke.
#
# The constraints, from the element declarations (D6) and the junction laws (5.4):
#
# * `p => (:effort_out, :fixed)` — the element determines the effort, so the stroke is at the
#   *other* end (Se, Ground, sensors, MSe);
# * `p => (:flow_out, :fixed)` — the element determines the flow, so the stroke is at its own
#   port (Sf, Fixed);
# * `p => :effort_out` / `:flow_out` (preferred) — the same, but only as a preference; a
#   storage element that has to give it up is in derivative causality (W201);
# * `(p1, p2) => :transformer` — effort in on one side is effort out on the other;
# * `(p1, p2) => :gyrator` — both sides are effort-in or both effort-out;
# * a port with no declaration is free (R);
# * a 0-junction has exactly one bond imposing effort (stroke at the junction), a 1-junction
#   exactly one bond imposing flow (stroke away from the junction).
#
# SCAP is the three ordered stages of plan 5.7: fixed causality with propagation, preferred
# integral causality on C/I with propagation, then arbitrary causality on what is left. A
# fixed element that cannot get its causality is E106; a storage element forced into
# derivative causality is W201; a component that only an arbitrary choice can solve is an
# algebraic loop, W202 (naming the free instances in it).

const CausalityMap = Dict{String,NamedTuple{(:strokeAt,),Tuple{String}}}

const _UNKNOWN_STROKE = :unknown

# ---------------------------------------------------------------------------------------
# The bond graph SCAP works on
# ---------------------------------------------------------------------------------------

"""    _ScapEnd(kind, path, port, node)

One end of a bond: `kind` is `:junction` or `:port`; `path` is the junction's or the
instance's path; `port` is the port symbol for `:port` ends."""
struct _ScapEnd
    kind::Symbol
    path::String
    port::Union{Symbol,Nothing}
    node::String
end

"""    _ScapGraph

The bond graph in the form SCAP needs: the bonds in connection order with their two ends,
the junction incidence, the causality declaration of every bonded port, and the
transformer/gyrator relations between bonded port pairs."""
struct _ScapGraph
    ids::Vector{String}
    ends::Dict{String,Tuple{_ScapEnd,_ScapEnd}}
    junction_kind::Dict{String,Int}
    junction_bonds::Dict{String,Vector{Tuple{String,Symbol}}}
    junction_order::Vector{String}
    port_decl::Dict{Tuple{String,Symbol},Tuple{Symbol,Symbol}}
    relations::Vector{Tuple{Symbol,Tuple{String,Symbol},Tuple{String,Symbol}}}
end

"""    _ScapConflict(kind, path, bonds, quantity)

Why a propagation stopped: `kind` is `:junction` (a junction law is violated), `:relation`
(a transformer/gyrator relation is violated) or `:decided` (a fixed element's bond was
already forced the other way). `bonds` are the offending bond ids, `quantity` is `:effort`
or `:flow` where one applies."""
struct _ScapConflict
    kind::Symbol
    path::String
    bonds::Vector{String}
    quantity::Symbol
end

"""    _ScapState(stroke)

The assignment in progress: the bond id → stroke side (`:from`, `:to` or `:unknown`)."""
mutable struct _ScapState
    stroke::Dict{String,Symbol}
end

function _scap_graph(b::Builder, plan::ConnPlan)
    ids = String[]
    ends = Dict{String,Tuple{_ScapEnd,_ScapEnd}}()
    junction_kind = Dict{String,Int}()
    junction_bonds = Dict{String,Vector{Tuple{String,Symbol}}}()
    junction_order = String[]
    port_decl = Dict{Tuple{String,Symbol},Tuple{Symbol,Symbol}}()
    relations = Tuple{Symbol,Tuple{String,Symbol},Tuple{String,Symbol}}[]
    seen_ports = Set{Tuple{String,Symbol}}()
    seen_relations = Set{String}()

    for junction in b.junctions
        junction_kind[junction.path] = junction.kind
        junction_bonds[junction.path] = Tuple{String,Symbol}[]
        push!(junction_order, junction.path)
    end

    for state in plan.states
        (state.valid && state.conn.kind == :bond) || continue
        f = _scap_end(state.from)
        t = _scap_end(state.to)
        (f === nothing || t === nothing) && continue
        id = state.conn.id
        push!(ids, id)
        ends[id] = (f, t)
        for (side, ep) in ((:from, f), (:to, t))
            ep.kind === :junction || continue
            haskey(junction_bonds, ep.path) || continue
            push!(junction_bonds[ep.path], (id, side))
        end
        for ep in (f, t)
            ep.kind === :port || continue
            key = (ep.path, ep.port::Symbol)
            key in seen_ports && continue
            push!(seen_ports, key)
            st = get(b.state_by_path, ep.path, nothing)
            st === nothing && continue
            _record_decl!(b, st, key, port_decl, relations, seen_relations)
        end
    end

    return _ScapGraph(ids, ends, junction_kind, junction_bonds, junction_order,
        port_decl, relations)
end

function _scap_end(ep::RawEndpoint)
    ep.kind === :junction && return _ScapEnd(:junction, ep.path, nothing, ep.node)
    ep.kind === :power && ep.port !== nothing &&
        return _ScapEnd(:port, ep.path, ep.port, ep.node)
    return nothing
end

function _record_decl!(
    b::Builder,
    st::BlockState,
    key::Tuple{String,Symbol},
    port_decl::Dict{Tuple{String,Symbol},Tuple{Symbol,Symbol}},
    relations::Vector{Tuple{Symbol,Tuple{String,Symbol},Tuple{String,Symbol}}},
    seen_relations::Set{String},
)
    for decl in BGSim.causality(st.pb)
        ports = BGSim.causality_ports(decl)
        kind = BGSim.causality_kind(decl)
        value = BGSim.causality_value(decl)
        if kind === :transformer || kind === :gyrator
            length(ports) == 2 || continue
            first_key = (st.path, ports[1])
            second_key = (st.path, ports[2])
            haskey(b.port_at, first_key) || continue
            haskey(b.port_at, second_key) || continue
            marker = st.path * "\0" * String(kind)
            marker in seen_relations && continue
            push!(seen_relations, marker)
            push!(relations, (kind, first_key, second_key))
        elseif kind === :fixed || kind === :preferred
            value === nothing && continue
            length(ports) == 1 || continue
            key == (st.path, ports[1]) || continue
            haskey(port_decl, key) || (port_decl[key] = (kind, value))
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# The constraints
# ---------------------------------------------------------------------------------------

# The functions below take the bond and the port side explicitly; the tiny helpers keep the
# assignment code readable.
_other_side(side::Symbol) = side === :from ? :to : :from

function _bond_end(graph::_ScapGraph, bond::String, side::Symbol)
    f, t = graph.ends[bond]
    return side === :from ? f : t
end

"""    _set_stroke!(st, graph, bond, side) -> Bool

Set a bond's stroke and return whether anything changed. A decided bond is never
overwritten."""
function _set_stroke!(st::_ScapState, bond::String, side::Symbol)
    st.stroke[bond] === _UNKNOWN_STROKE || return false
    st.stroke[bond] = side
    return true
end

"""    _propagate!(st, graph) -> Union{Nothing,_ScapConflict}

Enforce the junction and transformer/gyrator laws until nothing changes. Only undecided
bonds are written; a law that is violated by decided bonds is returned as a conflict."""
function _propagate!(st::_ScapState, graph::_ScapGraph)
    changed = true
    while changed
        changed = false
        for path in graph.junction_order
            isempty(graph.junction_bonds[path]) && continue
            kind = graph.junction_kind[path]
            here = 0
            away = 0
            unknown = String[]
            imposing = String[]
            for (bond, side) in graph.junction_bonds[path]
                stroke = st.stroke[bond]
                if stroke === _UNKNOWN_STROKE
                    push!(unknown, bond)
                elseif stroke === side
                    here += 1
                    kind == 0 && push!(imposing, bond)
                else
                    away += 1
                    kind == 1 && push!(imposing, bond)
                end
            end
            if kind == 0
                here > 1 && return _ScapConflict(:junction, path, imposing, :effort)
                if here == 0 && isempty(unknown)
                    return _ScapConflict(:junction, path, collect_bonds(graph, path), :effort)
                end
                if here == 1
                    for bond in unknown
                        changed |= _set_stroke!(st, bond, _other_side(_bond_side(graph, path, bond)))
                    end
                elseif here == 0 && length(unknown) == 1
                    bond = only(unknown)
                    changed |= _set_stroke!(st, bond, _bond_side(graph, path, bond))
                end
            else
                away > 1 && return _ScapConflict(:junction, path, imposing, :flow)
                if away == 0 && isempty(unknown)
                    return _ScapConflict(:junction, path, collect_bonds(graph, path), :flow)
                end
                if away == 1
                    for bond in unknown
                        changed |= _set_stroke!(st, bond, _bond_side(graph, path, bond))
                    end
                elseif away == 0 && length(unknown) == 1
                    bond = only(unknown)
                    changed |= _set_stroke!(st, bond, _other_side(_bond_side(graph, path, bond)))
                end
            end
        end
        for (kind, p1, p2) in graph.relations
            b1 = _port_bond(graph, p1)
            b2 = _port_bond(graph, p2)
            (b1 === nothing || b2 === nothing) && continue
            s1 = _port_stroke(graph, st, p1)
            s2 = _port_stroke(graph, st, p2)
            if s1 !== nothing && s2 !== nothing
                ok = kind === :transformer ? (s1 != s2) : (s1 == s2)
                ok && continue
                return _ScapConflict(:relation, first(p1), String[b1[1], b2[1]],
                    kind === :transformer ? :effort : :flow)
            elseif s1 !== nothing
                wanted = kind === :transformer ? !s1 : s1
                changed |= _force_port_stroke!(st, graph, p2, wanted)
            elseif s2 !== nothing
                wanted = kind === :transformer ? !s2 : s2
                changed |= _force_port_stroke!(st, graph, p1, wanted)
            end
        end
    end
    return nothing
end

_bond_side(graph::_ScapGraph, path::String, bond::String) = begin
    f, _ = graph.ends[bond]
    return f.kind === :junction && f.path == path ? :from : :to
end

function collect_bonds(graph::_ScapGraph, path::String)
    return String[bond for (bond, _) in graph.junction_bonds[path]]
end

function _port_bond(graph::_ScapGraph, key::Tuple{String,Symbol})
    for bond in graph.ids
        f, t = graph.ends[bond]
        f.kind === :port && (f.path, f.port) == key && return (bond, :from)
        t.kind === :port && (t.path, t.port) == key && return (bond, :to)
    end
    return nothing
end

"""    _port_stroke(graph, st, key) -> Union{Bool,Nothing}

Whether the state stroke of the port's bond is at the port (`true`), away from it (`false`)
or undecided (`nothing`)."""
function _port_stroke(graph::_ScapGraph, st::_ScapState, key::Tuple{String,Symbol})
    found = _port_bond(graph, key)
    found === nothing && return nothing
    bond, side = found
    stroke = st.stroke[bond]
    stroke === _UNKNOWN_STROKE && return nothing
    return stroke == side
end

"""    _force_port_stroke!(st, graph, key, at_port) -> Bool

Make a port's bond stroke land at the port (`at_port == true`) or away from it."""
function _force_port_stroke!(st::_ScapState, graph::_ScapGraph, key, at_port::Bool)
    found = _port_bond(graph, key)
    found === nothing && return false
    bond, side = found
    return _set_stroke!(st, bond, at_port ? side : _other_side(side))
end

# ---------------------------------------------------------------------------------------
# The three SCAP stages
# ---------------------------------------------------------------------------------------

"""    _try_stroke(st, graph, bond, side) -> (state, conflict)

Apply one stroke and propagate. On a conflict the input state is returned unchanged with the
conflict, so the caller can revoke the choice."""
function _try_stroke(st::_ScapState, graph::_ScapGraph, bond::String, side::Symbol)
    current = st.stroke[bond]
    if current === side
        return st, nothing
    elseif current !== _UNKNOWN_STROKE
        return st, _ScapConflict(:decided, "", String[bond], :effort)
    end
    candidate = _ScapState(copy(st.stroke))
    candidate.stroke[bond] = side
    conflict = _propagate!(candidate, graph)
    return conflict === nothing ? (candidate, nothing) : (st, conflict)
end

"""    _required_stroke(graph, key, value) -> Symbol

The bond side a fixed or preferred declaration asks for: `:effort_out` puts the stroke away
from the port, `:flow_out` at the port."""
function _required_stroke(graph::_ScapGraph, key::Tuple{String,Symbol}, value::Symbol)
    found = _port_bond(graph, key)
    found === nothing && return _UNKNOWN_STROKE
    bond, side = found
    return value === :flow_out ? side : _other_side(side)
end

function _fixed_ports(graph::_ScapGraph)
    out = Tuple{String,Symbol}[]
    for bond in graph.ids
        f, t = graph.ends[bond]
        for ep in (f, t)
            ep.kind === :port || continue
            key = (ep.path, ep.port::Symbol)
            decl = get(graph.port_decl, key, nothing)
            decl === nothing && continue
            decl[1] === :fixed || continue
            key in out || push!(out, key)
        end
    end
    return out
end

function _preferred_ports(graph::_ScapGraph)
    out = Tuple{String,Symbol}[]
    for bond in graph.ids
        f, t = graph.ends[bond]
        for ep in (f, t)
            ep.kind === :port || continue
            key = (ep.path, ep.port::Symbol)
            decl = get(graph.port_decl, key, nothing)
            decl === nothing && continue
            decl[1] === :preferred || continue
            key in out || push!(out, key)
        end
    end
    return out
end

"""    analyze_causality!(b, plan) -> CausalityMap

Run SCAP on the flattened bond graph and append W201, W202 and E106 to the builder's
diagnostics. The result maps every valid bond connection id to its stroke end (`:from` or
`:to`, where the effort is the input), which `model.check` hands to the editor."""
function analyze_causality!(b::Builder, plan::ConnPlan)
    graph = _scap_graph(b, plan)
    st = _ScapState(Dict(bond => _UNKNOWN_STROKE for bond in graph.ids))

    # 1. Fixed causality (Se, Sf, Ground, sensors, ...) with propagation.
    for key in _fixed_ports(graph)
        _, value = graph.port_decl[key]
        bond = _port_bond(graph, key)
        bond === nothing && continue
        target = _required_stroke(graph, key, value)
        target === _UNKNOWN_STROKE && continue
        new_state, conflict = _try_stroke(st, graph, bond[1], target)
        if conflict === nothing
            st = new_state
        else
            push!(b.diagnostics, _e106(b, graph, st, key, value, conflict))
        end
    end

    # 2. Preferred integral causality on the storage elements, with propagation. A
    #    preference that cannot be met is revoked here; the final check reports W201.
    for key in _preferred_ports(graph)
        _, value = graph.port_decl[key]
        bond = _port_bond(graph, key)
        bond === nothing && continue
        st.stroke[bond[1]] === _UNKNOWN_STROKE || continue
        target = _required_stroke(graph, key, value)
        new_state, conflict = _try_stroke(st, graph, bond[1], target)
        conflict === nothing && (st = new_state)
    end

    # 3. Arbitrary causality on what is left. A component that only such a choice can solve
    #    is an algebraic loop (W202); the free instances are named in the message.
    for component in _undecided_components(graph, st)
        isempty(component) && continue
        free = _free_instances(graph, component)
        isempty(free) || push!(b.diagnostics, _w202(b, graph, component, free))
        st = _assign_arbitrary!(st, graph, component)
    end

    # Storage elements that had to give up their preferred integral causality.
    for key in _preferred_ports(graph)
        _, value = graph.port_decl[key]
        at_port = _port_stroke(graph, st, key)
        at_port === nothing && continue
        preferred_at_port = value === :flow_out
        at_port == preferred_at_port && continue
        push!(b.diagnostics, _w201(b, key, _port_bond(graph, key)[1]))
    end

    return CausalityMap(
        bond => (strokeAt = st.stroke[bond] === :from ? "from" : "to",)
        for bond in graph.ids
    )
end

# ---------------------------------------------------------------------------------------
# Arbitrary choice
# ---------------------------------------------------------------------------------------

"""    _undecided_components(graph, st) -> Vector{Vector{String}}

The connected components of the still-undecided bonds, in connection order. Two bonds are
connected when they meet at a junction or at a (single-bond) port."""
function _undecided_components(graph::_ScapGraph, st::_ScapState)
    pending = Set(bond for bond in graph.ids if st.stroke[bond] === _UNKNOWN_STROKE)
    components = Vector{String}[]
    seen = Set{String}()
    for seed in graph.ids
        seed in pending || continue
        seed in seen && continue
        component = String[]
        queue = String[seed]
        push!(seen, seed)
        while !isempty(queue)
            bond = popfirst!(queue)
            push!(component, bond)
            for ep in _ends(graph, bond)
                neighbours = if ep.kind === :junction
                    collect_bonds(graph, ep.path)
                else
                    found = _port_bond(graph, (ep.path, ep.port::Symbol))
                    found === nothing ? String[] : String[found[1]]
                end
                for other in neighbours
                    other in pending || continue
                    other in seen && continue
                    push!(seen, other)
                    push!(queue, other)
                end
            end
        end
        push!(components, component)
    end
    return components
end

_ends(graph::_ScapGraph, bond::String) = graph.ends[bond]

"""    _free_instances(graph, component) -> Vector{String}

The instance paths in the component that have a power port without a causality declaration
(the R elements of the loop), in path order."""
function _free_instances(graph::_ScapGraph, component::Vector{String})
    paths = String[]
    for bond in component, ep in _ends(graph, bond)
        ep.kind === :port || continue
        haskey(graph.port_decl, (ep.path, ep.port::Symbol)) && continue
        ep.path in paths || push!(paths, ep.path)
    end
    sort!(paths)
    return paths
end

"""    _assign_arbitrary!(st, graph, component)

Give every undecided bond of `component` some causality, trying `:from` then `:to` and
keeping whatever propagation accepts. Bonds that remain (a torn loop) are stroked `:from` so
the editor always gets a complete result."""
function _assign_arbitrary!(st::_ScapState, graph::_ScapGraph, component::Vector{String})
    for _ in 1:(2 * length(component) + 2)
        progress = false
        for bond in component
            st.stroke[bond] === _UNKNOWN_STROKE || continue
            for side in (:from, :to)
                new_state, conflict = _try_stroke(st, graph, bond, side)
                if conflict === nothing
                    st = new_state
                    progress = true
                    break
                end
            end
        end
        progress || break
    end
    for bond in component
        st.stroke[bond] === _UNKNOWN_STROKE || continue
        st.stroke[bond] = :from
    end
    return st
end

# ---------------------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------------------

function _block_of(b::Builder, path::String)
    st = get(b.state_by_path, path, nothing)
    return st === nothing ? nothing : st.ref
end

function _node_of(b::Builder, path::String)
    st = get(b.state_by_path, path, nothing)
    return st === nothing ? nothing : st.node
end

"""    _e106(b, graph, st, key, value, conflict) -> Diagnostic

A fixed-causality element could not get its stroke. When the conflict is a junction with
another fixed element imposing the same quantity, the message names both, as the plan 3.4
sample does."""
function _e106(
    b::Builder,
    graph::_ScapGraph,
    st::_ScapState,
    key::Tuple{String,Symbol},
    value::Symbol,
    conflict::_ScapConflict,
)
    path = key[1]
    bond = _port_bond(graph, key)
    connection = bond === nothing ? nothing : bond[1]
    block = _block_of(b, path)
    node = _node_of(b, path)
    names = _conflict_names(graph, st, key, value, conflict)
    if length(names) >= 2
        quantity = conflict.quantity === :flow ? "flow" : "effort"
        jpath = _imposing_junction(graph, key, value)
        junction = jpath === nothing ? "junction" : _junction_label(graph, jpath)
        message = "causal conflict: $(join(names, " and ")) both impose the $quantity on the $junction"
    else
        message = "causal conflict: `$(path)` is fixed to $(value) causality but its bond is forced the other way"
    end
    return diag(
        "E106",
        message;
        hint = "remove one source, or insert an R between them",
        path = path,
        block = block,
        node = node,
        connection = connection,
    )
end

_junction_label(graph::_ScapGraph, path::String) =
    string(graph.junction_kind[path], "-junction")

"""    _imposing_junction(graph, key, value) -> Union{String,Nothing}

The junction a fixed element imposes on, when its required stroke lands at a junction end."""
function _imposing_junction(graph::_ScapGraph, key::Tuple{String,Symbol}, value::Symbol)
    bond = _port_bond(graph, key)
    bond === nothing && return nothing
    target = _required_stroke(graph, key, value)
    target === _UNKNOWN_STROKE && return nothing
    ep = _bond_end(graph, bond[1], target)
    return ep.kind === :junction && haskey(graph.junction_kind, ep.path) ? ep.path : nothing
end

"""    _conflict_names(graph, st, key, value, conflict) -> Vector{String}

The element names taking part in an E106: the other elements already imposing on the same
junction end of the processed port's bond, plus the processed element itself."""
function _conflict_names(
    graph::_ScapGraph,
    st::_ScapState,
    key::Tuple{String,Symbol},
    value::Symbol,
    conflict::_ScapConflict,
)
    bond = _port_bond(graph, key)
    bond === nothing && return String[]
    jpath = _imposing_junction(graph, key, value)
    if jpath !== nothing
        kind = graph.junction_kind[jpath]
        imposing = String[]
        for (other, side) in graph.junction_bonds[jpath]
            stroke = st.stroke[other]
            (stroke === _UNKNOWN_STROKE || other == bond[1]) && continue
            at = stroke == side
            (kind == 0 ? at : !at) && push!(imposing, other)
        end
        push!(imposing, bond[1])
        names = String[]
        for other in imposing
            for candidate in _ends(graph, other)
                candidate.kind === :port || continue
                name = _owner(candidate.path)
                name in names || push!(names, name)
            end
        end
        return names
    end
    if conflict.kind === :relation || conflict.kind === :junction
        names = String[]
        for other in conflict.bonds
            for candidate in _ends(graph, other)
                candidate.kind === :port || continue
                name = _owner(candidate.path)
                name in names || push!(names, name)
            end
        end
        return names
    end
    return String[]
end

function _w201(b::Builder, key::Tuple{String,Symbol}, bond::String)
    path = key[1]
    return diag(
        "W201",
        "$(_owner(path)) is in derivative causality; the DAE index is raised";
        hint = "split the storage element or add an I between the dependent elements",
        path = path,
        block = _block_of(b, path),
        node = _node_of(b, path),
        connection = bond,
    )
end

function _w202(b::Builder, graph::_ScapGraph, component::Vector{String}, free::Vector{String})
    names = [_owner(path) for path in free]
    first_path = first(free)
    first_bond = first(component)
    return diag(
        "W202",
        "algebraic loop through $(join(names, ", "))";
        hint = "insert a C or I element to break the loop",
        path = first_path,
        block = _block_of(b, first_path),
        node = _node_of(b, first_path),
        connection = first_bond,
    )
end

# ---------------------------------------------------------------------------------------
# After mtkcompile (plan 5.7, second paragraph)
# ---------------------------------------------------------------------------------------

"""    post_compile_warnings(flat, system) -> Vector{Diagnostic}

Plan 5.7: a variable that appears under `ddt` in the flat model but that `mtkcompile` did not
keep as a differential state is in derivative causality. `simulate` calls this right after
the lowering and merges the result into the run's diagnostics; this is how iconic models
(Spring, Mass, ...) get their W201 with the variable's origin path."""
function post_compile_warnings(flat::Flat.FlatModel, system)::Vector{Diagnostic}
    unknown_names = Set{String}()
    for unknown in BGSim.ModelingToolkit.unknowns(system)
        push!(unknown_names, BGSim.signal_name(unknown))
    end
    kept = Set{String}()
    for equation in BGSim.ModelingToolkit.equations(system)
        _collect_differentials!(kept, equation.lhs)
        _collect_differentials!(kept, equation.rhs)
    end
    # `mtkcompile` may keep the physical state under another name: in the iconic RLC it
    # integrates `C1/n.f` and leaves `L1/i ~ -C1/n.f` as an observed alias. Such a variable
    # is still integrated, so it is not in derivative causality. Follow observed definitions
    # to a fixpoint, but only through expressions that really depend on a state (a constant
    # or parameter alias is a constrained variable, not a state).
    changed = true
    while changed
        changed = false
        for equation in BGSim.ModelingToolkit.observed(system)
            lhs = _unwrap_num(equation.lhs)
            BGSim.ModelingToolkit.isvariable(lhs) || continue
            BGSim.ModelingToolkit.isparameter(lhs) && continue
            name = BGSim.signal_name(BGSim.Symbolics.wrap(lhs))
            name in kept && continue
            dependencies = Set{String}()
            has_derivative = Ref(false)
            _collect_unknown_refs!(dependencies, has_derivative, equation.rhs, unknown_names)
            has_derivative[] && continue
            isempty(dependencies) && continue
            all(dependency -> dependency in kept, dependencies) || continue
            push!(kept, name)
            changed = true
        end
    end
    out = Diagnostic[]
    seen = Set{String}()
    for equation in flat.equations
        ids = String[]
        _ddt_ids!(ids, equation.lhs)
        _ddt_ids!(ids, equation.rhs)
        for id in ids
            id in seen && continue
            id in kept && continue
            push!(seen, id)
            variable = _flat_variable(flat, id)
            variable === nothing && continue
            push!(out, _post_compile_w201(variable))
        end
    end
    return sort_diagnostics(out)
end

_unwrap_num(ex) = ex isa BGSim.Symbolics.Num ? BGSim.Symbolics.unwrap(ex) : ex

"""    _collect_unknown_refs!(names, has_derivative, ex, unknown_names)

Collect the unknown-variable names an observed expression depends on, and record whether it
contains a derivative term. Parameters, literals and `t` are not dependencies."""
function _collect_unknown_refs!(
    names::Set{String},
    has_derivative::Base.RefValue{Bool},
    ex,
    unknown_names::Set{String},
)
    ex === nothing && return nothing
    ex isa Number && return nothing
    ex = _unwrap_num(ex)
    if BGSim.ModelingToolkit.isdifferential(ex)
        has_derivative[] = true
        return nothing
    end
    if BGSim.ModelingToolkit.isvariable(ex)
        BGSim.ModelingToolkit.isparameter(ex) && return nothing
        name = BGSim.signal_name(BGSim.Symbolics.wrap(ex))
        name in unknown_names && push!(names, name)
        return nothing
    end
    BGSim.Symbolics.iscall(ex) || return nothing
    for argument in BGSim.Symbolics.arguments(ex)
        _collect_unknown_refs!(names, has_derivative, argument, unknown_names)
    end
    return nothing
end

function _collect_differentials!(kept::Set{String}, ex)
    ex === nothing && return nothing
    ex isa Number && return nothing
    ex isa BGSim.Symbolics.Num && (ex = BGSim.Symbolics.unwrap(ex))
    if BGSim.ModelingToolkit.isdifferential(ex)
        arguments = BGSim.Symbolics.arguments(ex)
        if !isempty(arguments)
            push!(kept, BGSim.signal_name(BGSim.Symbolics.wrap(first(arguments))))
        end
        return nothing
    end
    arguments = try
        BGSim.Symbolics.arguments(ex)
    catch
        nothing
    end
    arguments === nothing && return nothing
    for argument in arguments
        _collect_differentials!(kept, argument)
    end
    return nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.Call) = begin
    if ex.fn.name === :ddt && length(ex.args) == 1
        argument = ex.args[1]
        if argument isa BGSim.Name || argument isa BGSim.Field
            push!(out, Flat.flat_id(argument))
        end
    end
    for argument in ex.args
        _ddt_ids!(out, argument)
    end
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.Field) = _ddt_ids!(out, ex.base)

_ddt_ids!(out::Vector{String}, ex::BGSim.BinOp) = begin
    _ddt_ids!(out, ex.lhs)
    _ddt_ids!(out, ex.rhs)
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.Comparison) = begin
    _ddt_ids!(out, ex.lhs)
    _ddt_ids!(out, ex.rhs)
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.UnOp) = _ddt_ids!(out, ex.operand)

_ddt_ids!(out::Vector{String}, ex::BGSim.IfElse) = begin
    _ddt_ids!(out, ex.cond)
    _ddt_ids!(out, ex.then)
    _ddt_ids!(out, ex.otherwise)
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.BoolOp) = begin
    for operand in ex.operands
        _ddt_ids!(out, operand)
    end
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.Index) = begin
    _ddt_ids!(out, ex.base)
    for index in ex.indices
        _ddt_ids!(out, index)
    end
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.VectorLit) = begin
    for element in ex.elements
        _ddt_ids!(out, element)
    end
    nothing
end

_ddt_ids!(out::Vector{String}, ex::BGSim.MatrixLit) = begin
    for row in ex.rows, element in row
        _ddt_ids!(out, element)
    end
    nothing
end

_ddt_ids!(::Vector{String}, ::Any) = nothing

function _flat_variable(flat::Flat.FlatModel, id::String)
    for variable in flat.variables
        variable.id == id && return variable
    end
    return nothing
end

function _post_compile_w201(variable::Flat.FlatVar)
    origin = variable.origin
    block = origin.block
    source = origin.range === nothing || block === nothing ? nothing :
             BGSim.SourceRef(BGSim.source_kind(block), block, origin.range)
    return diag(
        "W201",
        "`$(variable.id)` appears under ddt but was not kept as a differential state; the DAE index is raised";
        hint = "split the storage element or add an I between the dependent elements",
        path = origin.path,
        block = block,
        source = source,
        node = origin.node,
    )
end
