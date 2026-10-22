# Domain adoption (plan 5.6, decision D9) and the unit-factor pass (plan 5.3).
#
# The union-find runs over bond islands: every bond joins its two endpoints, and every
# junction is the shared endpoint of all its bonds, so the whole connected bond graph falls
# out as one component. Each component collects the *concrete* domains its ports declare
# (`Electrical`, `Translation`, `Rotation`, `Hydraulic`):
#
# | concrete domains in the island | result |
# | --- | --- |
# | 0 | dimensionless `Generic`, W205 (D14: accepted, warned) |
# | 1 | adopted by every Generic port and every bond in the island |
# | > 1 | E102 naming two ports of the island |
#
# Wire nodes are their own union-find components: plan 5.5 allows only concrete-domain ports
# on a wire, all of one domain, so a wire node's domain is the domain of its ports.
#
# Adoption then substitutes the `effort`/`flow` pseudo-dimensions of a Generic block's
# declarations (D9: a `C` on an electrical bond takes farads) and gives every port field the
# effort/flow dimension of its adopted domain. Finally `apply_domains!` inserts unit factors
# for scale-only differences (plan 5.3: returned to the editor as `unitFactors`) and reports
# a dimension mismatch on a connection as E102.

"""    UnionFind

A tiny union-find over `Tuple{String,Symbol}` keys (instance path + port name, or a
junction key). It is deliberately local rather than a package: the components are small and
the API is four functions."""
mutable struct UnionFind
    parent::Dict{Tuple{String,Symbol},Tuple{String,Symbol}}
end

UnionFind() = UnionFind(Dict{Tuple{String,Symbol},Tuple{String,Symbol}}())

function _uf_push!(uf::UnionFind, key::Tuple{String,Symbol})
    haskey(uf.parent, key) || (uf.parent[key] = key)
    return nothing
end

function _uf_find!(uf::UnionFind, key::Tuple{String,Symbol})
    _uf_push!(uf, key)
    root = key
    while uf.parent[root] != root
        root = uf.parent[root]
    end
    x = key
    while uf.parent[x] != root
        next = uf.parent[x]
        uf.parent[x] = root
        x = next
    end
    return root
end

function _uf_union!(uf::UnionFind, a::Tuple{String,Symbol}, b::Tuple{String,Symbol})
    ra = _uf_find!(uf, a)
    rb = _uf_find!(uf, b)
    ra == rb && return ra
    uf.parent[rb] = ra
    return ra
end

_junction_key(path::String) = ("junction:" * path, Symbol(""))

_endpoint_key(ep::RawEndpoint) =
    ep.kind == :junction ? _junction_key(ep.path) : _portkey(ep)

"""    _Island

One connected bond component while its domain is being decided: its ports (in connection
order), its junctions and the connection indices of its bonds, plus the first port seen for
each declared domain (so the E102 message can name two real ports)."""
struct _Island
    ports::Vector{Tuple{String,Symbol}}
    junctions::Vector{String}
    bonds::Vector{Int}
    by_domain::Dict{Symbol,Vector{Tuple{String,Symbol}}}
    domain_order::Vector{Symbol}
end

_Island() = _Island(
    Tuple{String,Symbol}[],
    String[],
    Int[],
    Dict{Symbol,Vector{Tuple{String,Symbol}}}(),
    Symbol[],
)

function _port_state(b::Builder, key::Tuple{String,Symbol})
    path, name = key
    st = get(b.state_by_path, path, nothing)
    st === nothing && return nothing
    return get(b.port_at, key, nothing)
end

function _port_node(b::Builder, key::Tuple{String,Symbol})
    path, _ = key
    st = get(b.state_by_path, path, nothing)
    return st === nothing ? nothing : st.node
end

function _port_ref(b::Builder, key::Tuple{String,Symbol})
    path, _ = key
    st = get(b.state_by_path, path, nothing)
    return st === nothing ? nothing : st.ref
end

"""    resolve_domains!(b, plan) -> Dict{String,String}

Run the plan 5.6 union-find, decide one domain per bond island and wire node, report W205
for a dimensionless island and E102 for an island with two concrete domains, and fill
`plan.port_domains` (the adopted domain of every connected port, plus a key per junction).
Returns the editor's `domains` map (connection id -> domain name) for bonds and wires."""
function resolve_domains!(b::Builder, plan::ConnPlan)
    domains = Dict{String,String}()
    _resolve_bond_islands!(b, plan, domains)
    _resolve_wire_nodes!(b, plan, domains)
    return domains
end

function _resolve_bond_islands!(
    b::Builder,
    plan::ConnPlan,
    domains::Dict{String,String},
)
    uf = UnionFind()
    bond_indices = Int[]
    for (i, state) in enumerate(plan.states)
        (state.valid && state.conn.kind == :bond) || continue
        push!(bond_indices, i)
        _uf_union!(uf, _endpoint_key(state.from), _endpoint_key(state.to))
    end
    isempty(bond_indices) && return nothing
    islands = Dict{Tuple{String,Symbol},_Island}()
    order = Tuple{String,Symbol}[]
    for i in bond_indices
        state = plan.states[i]
        root = _uf_find!(uf, _endpoint_key(state.from))
        island = get(islands, root, nothing)
        if island === nothing
            island = _Island()
            islands[root] = island
            push!(order, root)
        end
        push!(island.bonds, i)
        for ep in (state.from, state.to)
            if ep.kind == :junction
                ep.path in island.junctions || push!(island.junctions, ep.path)
                continue
            end
            port = _port_state(b, _portkey(ep))
            port === nothing && continue
            key = _portkey(ep)
            key in island.ports || push!(island.ports, key)
            port.domain in island.domain_order || push!(island.domain_order, port.domain)
            list = get!(island.by_domain, port.domain, Tuple{String,Symbol}[])
            key in list || push!(list, key)
        end
    end
    for root in order
        island = islands[root]
        concrete = Symbol[d for d in island.domain_order if d != :Generic]
        if length(concrete) > 1
            _report_island_conflict!(b, plan, island, concrete)
            for i in island.bonds
                plan.states[i].valid = false
            end
            continue
        end
        adopted = isempty(concrete) ? :Generic : concrete[1]
        if isempty(concrete)
            _report_w205!(b, plan, island)
        end
        for i in island.bonds
            state = plan.states[i]
            state.domain = adopted
            domains[state.conn.id] = String(adopted)
        end
        for key in island.ports
            plan.port_domains[key] = adopted
        end
        for path in island.junctions
            plan.port_domains[_junction_key(path)] = adopted
        end
    end
    return nothing
end

function _report_w205!(b::Builder, plan::ConnPlan, island::_Island)
    first_bond = plan.states[island.bonds[1]].conn.id
    if !isempty(island.ports)
        path, name = island.ports[1]
        push!(
            b.diagnostics,
            diag(
                "W205",
                "bond island has no concrete domain; it is treated as dimensionless";
                hint = "connect the island to an Electrical, Translation, Rotation or Hydraulic port",
                path = path,
                block = _port_ref(b, island.ports[1]),
                node = _port_node(b, island.ports[1]),
                connection = first_bond,
            ),
        )
    else
        path = _owner(island.junctions[1])
        push!(
            b.diagnostics,
            diag(
                "W205",
                "bond island has no concrete domain; it is treated as dimensionless";
                hint = "connect the island to an Electrical, Translation, Rotation or Hydraulic port",
                path = path,
                node = _junction_node(b, island.junctions[1]),
                connection = first_bond,
            ),
        )
    end
    return nothing
end

function _junction_node(b::Builder, path::String)
    idx = get(b.junction_by_path, path, 0)
    return idx == 0 ? nothing : b.junctions[idx].node
end

function _report_island_conflict!(
    b::Builder,
    plan::ConnPlan,
    island::_Island,
    concrete::Vector{Symbol},
)
    a_domain = concrete[1]
    b_domain = concrete[2]
    a_key = island.by_domain[a_domain][1]
    b_key = island.by_domain[b_domain][1]
    a_port = _port_state(b, a_key)
    b_port = _port_state(b, b_key)
    (a_port === nothing || b_port === nothing) && return nothing
    connection = _bond_for(plan, island, b_key)
    push!(
        b.diagnostics,
        diag(
            "E102",
            "domain mismatch: $(a_domain) port `$(a_port.name)` of `$(_owner(a_key[1]))` is bonded to $(b_domain) port `$(b_port.name)` of `$(_owner(b_key[1]))`";
            hint = "cross domains only through a converter (DCMotor, IdealGear, Rack and pinion)",
            path = b_key[1],
            block = _port_ref(b, b_key),
            node = _port_node(b, b_key),
            connection = connection,
        ),
    )
    return nothing
end

function _bond_for(plan::ConnPlan, island::_Island, key::Tuple{String,Symbol})
    for i in island.bonds
        state = plan.states[i]
        (_endpoint_key(state.from) == key || _endpoint_key(state.to) == key) &&
            return state.conn.id
    end
    return isempty(island.bonds) ? nothing : plan.states[island.bonds[1]].conn.id
end

function _resolve_wire_nodes!(
    b::Builder,
    plan::ConnPlan,
    domains::Dict{String,String},
)
    for group in plan.wires
        group.valid || continue
        declared = Symbol[]
        seen = Tuple{String,Symbol}[]
        for key in group.ports
            port = get(b.port_at, key, nothing)
            port === nothing && continue
            port.domain in declared || push!(declared, port.domain)
            push!(seen, key)
        end
        if length(declared) > 1
            first_port = get(b.port_at, seen[1], nothing)
            second_key = seen[1]
            second_port = first_port
            for key in seen[2:end]
                cand = get(b.port_at, key, nothing)
                cand === nothing && continue
                if cand.domain != first_port.domain
                    second_key = key
                    second_port = cand
                    break
                end
            end
            push!(
                b.diagnostics,
                diag(
                    "E102",
                    "domain mismatch: $(first_port.domain) port `$(first_port.name)` of `$(_owner(seen[1][1]))` is wired to $(second_port.domain) port `$(second_port.name)` of `$(_owner(second_key[1]))`";
                    hint = "cross domains only through a converter (DCMotor, IdealGear, Rack and pinion)",
                    path = second_key[1],
                    block = _port_ref(b, second_key),
                    node = _port_node(b, second_key),
                    connection = isempty(group.edges) ? nothing :
                                 b.raw[group.edges[1]].conn.id,
                ),
            )
            group.valid = false
            continue
        end
        adopted = isempty(declared) ? :Generic : declared[1]
        group.domain = adopted
        for key in group.ports
            plan.port_domains[key] = adopted
        end
        for i in group.edges
            state = plan.states[i]
            state.valid || continue
            state.domain = adopted
            domains[state.conn.id] = String(adopted)
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Units: adoption of Generic declarations, power signals and unit factors
# ---------------------------------------------------------------------------------------

function _set_var_unit!(b::Builder, id::String, unit)
    v = var_by_id(b, id)
    v === nothing && return nothing
    v.unit = unit
    return nothing
end

function _set_param_unit!(b::Builder, id::String, unit)
    haskey(b.param_index, id) || return nothing
    p = b.params[b.param_index[id]]
    # FlatParam is immutable; replace in place.
    b.params[b.param_index[id]] = Flat.FlatParam(
        p.id,
        p.name,
        p.value,
        p.type,
        unit,
        p.attrs,
        p.origin,
    )
    return nothing
end

"""    apply_domains!(b, plan) -> Dict{String,Float64}

Second half of adoption: give every Generic instance the domain its islands adopted,
substitute `effort`/`flow` in its declaration units (D9), set every port field's unit to
the effort/flow dimension of its adopted domain, build the derived power signal `e*f` of
every port (D15), and compute the unit conversion factor of every connection. A mismatch is
E102 and invalidates the connection."""
function apply_domains!(b::Builder, plan::ConnPlan)
    _apply_instance_domains!(b, plan)
    _build_power_signals!(b, plan)
    return _compute_unit_factors!(b, plan)
end

function _apply_instance_domains!(b::Builder, plan::ConnPlan)
    for st in b.states
        doms = Symbol[]
        for (name, _) in st.ports
            adopted = get(plan.port_domains, _portkey(st.path, name), nothing)
            adopted === nothing && continue
            adopted in doms || push!(doms, adopted)
        end
        st.adopted = st.domain
        if st.domain == :Generic && !isempty(doms)
            concrete = Symbol[d for d in doms if d != :Generic]
            if length(unique(doms)) > 1 && !isempty(concrete)
                push!(
                    b.diagnostics,
                    diag(
                        "E102",
                        "`$(st.path)` connects islands with different domains ($(join(string.(unique(doms)), ", "))); a Generic block can only adopt one domain";
                        hint = "give the block a concrete port domain, or split it into two blocks",
                        path = st.path,
                        block = st.ref,
                        node = st.node,
                    ),
                )
            end
            st.adopted = isempty(concrete) ? :Generic : concrete[1]
        end
        # Substitute the pseudo-dimensions of the declarations when the block is Generic.
        if st.domain == :Generic && st.adopted != :Generic
            for (name, ids) in st.ids
                unit = get(st.units, name, nothing)
                unit === nothing && continue
                BGSim.Units.has_pseudo_dimensions(unit) || continue
                substituted = BGSim.Units.substitute_domain(unit, st.adopted)
                for id in ids
                    _set_var_unit!(b, id, substituted)
                    _set_param_unit!(b, id, substituted)
                end
            end
        end
        # Port fields take the effort/flow dimension of their adopted (or declared) domain.
        for (name, port) in st.ports
            adopted = get(plan.port_domains, _portkey(st.path, name), port.domain)
            eunit = BGSim.Units.effort_dims(adopted)
            funit = BGSim.Units.flow_dims(adopted)
            for id in port.eids
                _set_var_unit!(b, id, eunit)
            end
            for id in port.fids
                _set_var_unit!(b, id, funit)
            end
        end
    end
    # A junction-to-junction bond's virtual variables belong to the junction's island.
    for state in plan.states
        (state.conn.kind == :bond && state.domain !== nothing) || continue
        state.from.kind == :junction && state.to.kind == :junction || continue
        _set_var_unit!(b, state.conn.id * ".e", BGSim.Units.effort_dims(state.domain))
        _set_var_unit!(b, state.conn.id * ".f", BGSim.Units.flow_dims(state.domain))
    end
    return nothing
end

function _build_power_signals!(b::Builder, plan::ConnPlan)
    r = _placeholder_range()
    for st in b.states
        for (name, port) in st.ports
            adopted = get(plan.port_domains, _portkey(st.path, name), port.domain)
            eunit = BGSim.Units.effort_dims(adopted)
            funit = BGSim.Units.flow_dims(adopted)
            terms = BGSim.Expr[]
            for k in 1:port.size
                e = port_field_exprs(port, :e)[k]
                f = port_field_exprs(port, :f)[k]
                push!(terms, BinOp(:*, e, f, r))
            end
            id = port.qname * ".P"
            b.power_signals[id] = Flat.DerivedSignal(
                id,
                :power,
                eunit * funit,
                st.path,
                :Real,
                _sum_exprs(terms, r),
            )
        end
    end
    return nothing
end

function _field_unit(b::Builder, port::PortInfo, field::Symbol, k::Int)
    ids = field === :e ? port.eids : port.fids
    k <= length(ids) || return nothing
    v = var_by_id(b, ids[k])
    return v === nothing ? nothing : v.unit
end

function _dims_match(a, b)
    (a === nothing || b === nothing) && return true
    return a.exps == b.exps
end

function _factor_between(a, b)
    (a === nothing || b === nothing) && return 1.0
    a.exps == b.exps || return 1.0
    return a.scale / b.scale
end

function _compute_unit_factors!(b::Builder, plan::ConnPlan)
    unit_factors = Dict{String,Float64}()
    for state in plan.states
        state.valid || continue
        if state.conn.kind == :wire || state.conn.kind == :bond
            pf = get(b.port_at, _portkey(state.from), nothing)
            pt = get(b.port_at, _portkey(state.to), nothing)
            (pf === nothing || pt === nothing) && continue
            field = state.conn.kind == :wire ? across_field(state.domain) : :e
            unit_from = _field_unit(b, pf, field, 1)
            unit_to = _field_unit(b, pt, field, 1)
            mismatch = false
            for k in 1:max(pf.size, pt.size)
                a = _field_unit(b, pf, field, k)
                c = _field_unit(b, pt, field, k)
                if !_dims_match(a, c)
                    mismatch = true
                    break
                end
            end
            if state.conn.kind == :bond
                for k in 1:max(pf.size, pt.size)
                    a = _field_unit(b, pf, :f, k)
                    c = _field_unit(b, pt, :f, k)
                    if !_dims_match(a, c)
                        mismatch = true
                        break
                    end
                end
            end
            if mismatch
                _connection_diag!(
                    b,
                    state.to;
                    code = "E102",
                    message = "unit mismatch on connection `$(state.conn.id)`: " *
                              "$(_unit_label(unit_from)) and $(_unit_label(unit_to)) cannot be converted",
                    hint = "the two ends of a power connection must have one dimension",
                    connection = state.conn.id,
                )
                state.valid = false
                continue
            end
            factor = _factor_between(unit_from, unit_to)
            state.factor = factor
            unit_factors[state.conn.id] = factor
        elseif state.conn.kind == :signal
            from_st = get(b.state_by_path, state.from.path, nothing)
            to_st = get(b.state_by_path, state.to.path, nothing)
            (from_st === nothing || to_st === nothing) && continue
            from_ids = get(from_st.ids, something(state.from.port, Symbol("")), String[])
            to_ids = get(to_st.ids, something(state.to.port, Symbol("")), String[])
            (isempty(from_ids) || isempty(to_ids)) && continue
            out_var = var_by_id(b, from_ids[1])
            in_var = var_by_id(b, to_ids[1])
            (out_var === nothing || in_var === nothing) && continue
            if !_dims_match(out_var.unit, in_var.unit)
                _connection_diag!(
                    b,
                    state.to;
                    code = "E102",
                    message = "unit mismatch: output `$(state.from.port)` of `$(_owner(state.from.path))` is $(_unit_label(out_var.unit)) but input `$(state.to.port)` of `$(_owner(state.to.path))` is $(_unit_label(in_var.unit))",
                    hint = "connect signals of one dimension, or insert a conversion block",
                    connection = state.conn.id,
                )
                state.valid = false
                continue
            end
            factor = _factor_between(out_var.unit, in_var.unit)
            state.factor = factor
            factor == 1.0 || (unit_factors[state.conn.id] = factor)
        end
    end
    return unit_factors
end

_unit_label(d) = d === nothing ? "[?]" : "[" * BGSim.Units.unit_string(d) * "]"
