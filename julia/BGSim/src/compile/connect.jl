# Connection semantics (plan 5.5, decision D7): bonds, wires and signals.
#
# `classify_connections!` is the checking pass: it resolves every endpoint, enforces the
# three connection rules, rejects two sources on one input (E102), a wire on a Generic port
# and a bond between two concrete ports, and records which ports and inputs were *tried*
# (so an invalid connection does not also produce a spurious "unconnected" E101). It also
# builds the wire nodes (union-find over wire connections) and the junction bond lists.
#
# `emit_connections!` is the equation pass, run *after* domain adoption so every wire and
# bond knows its adopted domain and unit factor: a wire node of `k` ports gets `k`
# equations (plan 5.5: the across variables are equal, the through variables sum to zero),
# an element-to-element bond gets the two equations of plan 5.5, and a signal connection
# gets `input = output` (with the unit factor, if any).
#
# A bond touching a junction contributes no equation of its own: its two variables *are* the
# attached port's `e`/`f`, and the junction's `n` constraints (plan 5.4) are the connection
# equations. That accounting is what makes the fixture counts balance (see the WP report).

"""    ConnState(conn, from, to, valid, domain, factor)

One connection with its resolved endpoints. `valid` is cleared by any E102 (or by a domain
conflict found in `domains.jl`); `domain` is the adopted power domain; `factor` is the unit
conversion inserted by the compiler (1.0 when none)."""
mutable struct ConnState
    conn::IR.ModelConnection
    from::RawEndpoint
    to::RawEndpoint
    valid::Bool
    domain::Union{Symbol,Nothing}
    factor::Float64
end

"""    WireGroup(ports, edges, domain, valid)

One wire node: the ports joined by wire connections (union-find), the connection indices
that join them, and the adopted domain. A node of `k` ports gets `k` equations."""
mutable struct WireGroup
    ports::Vector{Tuple{String,Symbol}}
    edges::Vector{Int}
    domain::Symbol
    valid::Bool
end

"""    ConnPlan

Everything `connect.jl` computed about a model's connections, shared with `domains.jl`
(which fills in domains and factors), `junctions.jl` (which emits the constraints) and
`balance.jl` (which uses the attempt sets to avoid double diagnostics)."""
mutable struct ConnPlan
    states::Vector{ConnState}
    wires::Vector{WireGroup}
    wire_of_conn::Dict{Int,Int}
    attempts::Dict{Tuple{String,Symbol},Vector{Int}}
    bond_attempts::Dict{Tuple{String,Symbol},Vector{Int}}
    input_attempts::Dict{Tuple{String,Symbol},Vector{Int}}
    port_domains::Dict{Tuple{String,Symbol},Symbol}
end

_portkey(ep::RawEndpoint) = (ep.path, something(ep.port, Symbol("")))
_portkey(path::String, port::Symbol) = (path, port)

_owner(path::String) = isempty(path) ? "?" : split(path, '/')[end]

function _endpoint_label(ep::RawEndpoint)
    ep.kind == :junction && return "junction `$(_owner(ep.path))`"
    ep.port === nothing && return "`$(ep.path)`"
    return "`$(ep.port)` of `$(_owner(ep.path))`"
end

_endpoint_block(b::Builder, ep::RawEndpoint) =
    haskey(b.state_by_path, ep.path) ? b.state_by_path[ep.path].ref : nothing

function _connection_diag!(
    b::Builder,
    ep::RawEndpoint;
    code,
    message,
    hint = nothing,
    connection,
    path = ep.path,
    node = ep.node,
    block = _endpoint_block(b, ep),
)
    push!(
        b.diagnostics,
        diag(
            code,
            message;
            hint = hint,
            path = isempty(path) ? nothing : path,
            block = block,
            node = isempty(node) ? nothing : node,
            connection = connection,
        ),
    )
    return nothing
end

# ---------------------------------------------------------------------------------------
# Classification and checking
# ---------------------------------------------------------------------------------------

function classify_connections!(b::Builder)
    states = ConnState[]
    attempts = Dict{Tuple{String,Symbol},Vector{Int}}()
    bond_attempts = Dict{Tuple{String,Symbol},Vector{Int}}()
    inputs = Dict{Tuple{String,Symbol},Vector{Int}}()
    # Any connection *attempt* on a power port or an input suppresses the "unconnected"
    # E101, even when the attempt itself is invalid: the E102 already points at the problem.
    for (i, raw) in enumerate(b.raw)
        for ep in (raw.from, raw.to)
            ep.kind == :power && push!(get!(attempts, _portkey(ep), Int[]), i)
            ep.kind == :input && push!(get!(inputs, _portkey(ep), Int[]), i)
        end
    end
    sources = Dict{Tuple{String,Symbol},Int}()
    for (i, raw) in enumerate(b.raw)
        state = ConnState(raw.conn, raw.from, raw.to, true, nothing, 1.0)
        push!(states, state)
        _classify_one!(b, state, i, attempts, bond_attempts, sources)
    end
    _check_port_conflicts!(b, states)
    _record_junction_bonds!(b, states)
    wires, wire_of_conn = _build_wire_groups!(states)
    return ConnPlan(
        states,
        wires,
        wire_of_conn,
        attempts,
        bond_attempts,
        inputs,
        Dict{Tuple{String,Symbol},Symbol}(),
    )
end
function _classify_one!(
    b::Builder,
    state::ConnState,
    index::Int,
    attempts::Dict{Tuple{String,Symbol},Vector{Int}},
    bond_attempts::Dict{Tuple{String,Symbol},Vector{Int}},
    sources::Dict{Tuple{String,Symbol},Int},
)
    c = state.conn
    f = state.from
    t = state.to
    if f.kind == :unknown || t.kind == :unknown
        bad = f.kind == :unknown ? f : t
        message = if isempty(bad.path)
            "connection `$(c.id)` refers to unknown node `$(bad.node)`"
        else
            "connection `$(c.id)` refers to `$(something(bad.port, Symbol("?")))`, which is not a port of `$(_owner(bad.path))`"
        end
        _connection_diag!(b, bad; code = "E102", message = message, connection = c.id)
        state.valid = false
        return nothing
    end
    if c.kind == :signal
        _classify_signal!(b, state, sources)
    elseif c.kind == :wire
        _classify_wire!(b, state)
    elseif c.kind == :bond
        _classify_bond!(b, state, index, attempts, bond_attempts)
    else
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "connection `$(c.id)` has unknown kind `$(c.kind)`",
            connection = c.id,
        )
        state.valid = false
    end
    return nothing
end

function _classify_signal!(
    b::Builder,
    state::ConnState,
    sources::Dict{Tuple{String,Symbol},Int},
)
    c = state.conn
    f = state.from
    t = state.to
    if f.kind != :output || t.kind != :input
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "a signal connection goes from an output to an input: " *
                      "$(_endpoint_label(f)) is a $(f.kind) and $(_endpoint_label(t)) is a $(t.kind)",
            hint = "signal connections carry one output to one or more inputs",
            connection = c.id,
        )
        state.valid = false
        return nothing
    end
    key = _portkey(t)
    count = get(sources, key, 0) + 1
    sources[key] = count
    if count > 1
        previous = _previous_source(b, state)
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "input `$(t.port)` of `$(_owner(t.path))` has two sources" *
                      (previous === nothing ? "" : " (`$previous` and `$(c.id)`)"),
            hint = "an input has exactly one source; remove one of the connections",
            connection = c.id,
        )
        state.valid = false
    end
    # Sizes must match, so the element-wise assignment is complete.
    nf = _signal_size(b, f)
    nt = _signal_size(b, t)
    if nf > 0 && nt > 0 && nf != nt
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "a signal connection needs matching sizes: `$(f.port)` of `$(_owner(f.path))` has $nf values and `$(t.port)` of `$(_owner(t.path))` has $nt",
            connection = c.id,
        )
        state.valid = false
    end
    return nothing
end

_previous_source(b::Builder, state::ConnState) = begin
    key = _portkey(state.to)
    previous = nothing
    for raw in b.raw
        raw.conn.id == state.conn.id && break
        (raw.conn.kind == :signal && raw.to.kind == :input) || continue
        if _portkey(raw.to) == key
            previous = raw.conn.id
            break
        end
    end
    previous
end

function _signal_size(b::Builder, ep::RawEndpoint)
    st = get(b.state_by_path, ep.path, nothing)
    st === nothing && return 0
    ep.port === nothing && return 0
    ids = get(st.ids, ep.port, String[])
    return length(ids)
end

function _declared_port(b::Builder, ep::RawEndpoint)
    return get(b.port_at, _portkey(ep), nothing)
end

function _classify_wire!(
    b::Builder,
    state::ConnState,
)
    c = state.conn
    f = state.from
    t = state.to
    if f.kind != :power || t.kind != :power
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "a wire connects power ports: $(_endpoint_label(f)) is a $(f.kind) and $(_endpoint_label(t)) is a $(t.kind)",
            hint = "connect power ports with a wire or a bond, and signals with a signal connection",
            connection = c.id,
        )
        state.valid = false
        return nothing
    end
    pf = _declared_port(b, f)
    pt = _declared_port(b, t)
    if pf === nothing || pt === nothing
        state.valid = false
        return nothing
    end
    if pf.domain == :Generic || pt.domain == :Generic
        generic = pf.domain == :Generic ? f : t
        _connection_diag!(
            b,
            generic;
            code = "E102",
            message = "a wire needs concrete-domain power ports: $(_endpoint_label(generic)) is `Generic`",
            hint = "use a bond to attach a Generic port (bond graph element or junction)",
            connection = c.id,
        )
        state.valid = false
        return nothing
    end
    if pf.domain != pt.domain
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "domain mismatch: $(pf.domain) port `$(pf.name)` of `$(_owner(f.path))` is wired to $(pt.domain) port `$(pt.name)` of `$(_owner(t.path))`",
            hint = "cross domains only through a converter (DCMotor, IdealGear, Rack and pinion)",
            connection = c.id,
        )
        state.valid = false
    end
    return nothing
end

function _classify_bond!(
    b::Builder,
    state::ConnState,
    index::Int,
    attempts::Dict{Tuple{String,Symbol},Vector{Int}},
    bond_attempts::Dict{Tuple{String,Symbol},Vector{Int}},
)
    c = state.conn
    f = state.from
    t = state.to
    if !((f.kind == :power || f.kind == :junction) &&
         (t.kind == :power || t.kind == :junction))
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "a bond connects power ports or junctions: $(_endpoint_label(f)) is a $(f.kind) and $(_endpoint_label(t)) is a $(t.kind)",
            connection = c.id,
        )
        state.valid = false
        return nothing
    end
    pf = f.kind == :power ? _declared_port(b, f) : nothing
    pt = t.kind == :power ? _declared_port(b, t) : nothing
    if (f.kind == :power && pf === nothing) || (t.kind == :power && pt === nothing)
        state.valid = false
        return nothing
    end
    if pf !== nothing && pt !== nothing && pf.domain != :Generic && pt.domain != :Generic
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "a bond needs at least one Generic port or a junction: $(pf.domain) port `$(pf.name)` of `$(_owner(f.path))` and $(pt.domain) port `$(pt.name)` of `$(_owner(t.path))` are both concrete",
            hint = "connect two concrete ports of one domain with a wire",
            connection = c.id,
        )
        state.valid = false
        return nothing
    end
    for (ep, port) in ((f, pf), (t, pt))
        port === nothing && continue
        key = _portkey(ep)
        push!(get!(bond_attempts, key, Int[]), index)
        if length(bond_attempts[key]) > 1
            previous_id = b.raw[bond_attempts[key][1]].conn.id
            _connection_diag!(
                b,
                ep;
                code = "E102",
                message = "power port `$(port.name)` of `$(_owner(ep.path))` already has a bond (`$previous_id`)",
                hint = "a power port carries exactly one bond",
                connection = c.id,
            )
            state.valid = false
        end
        if port.size > 1 && (f.kind == :junction || t.kind == :junction)
            _connection_diag!(
                b,
                ep;
                code = "E102",
                message = "a junction needs scalar power ports: `$(port.name)` of `$(_owner(ep.path))` has $(port.size) components",
                hint = "bond-graph junctions are scalar; use a converter block for vectors",
                connection = c.id,
            )
            state.valid = false
        end
    end
    if pf !== nothing && pt !== nothing && pf.size != pt.size
        _connection_diag!(
            b,
            t;
            code = "E102",
            message = "a bond needs matching port sizes: `$(pf.name)` has $(pf.size) and `$(pt.name)` has $(pt.size)",
            connection = c.id,
        )
        state.valid = false
    end
    return nothing
end

"""    _check_port_conflicts!(b, states)

A power port belongs either to one bond or to one wire node (plan 5.5); the two connection
kinds are not interchangeable. A port that appears in both is E102 on the later connection,
and both connections are dropped so no nonsense equation is emitted."""
function _check_port_conflicts!(b::Builder, states::Vector{ConnState})
    wire_keys = Dict{Tuple{String,Symbol},Vector{Int}}()
    for (i, state) in enumerate(states)
        (state.valid && state.conn.kind == :wire) || continue
        push!(get!(wire_keys, _portkey(state.from), Int[]), i)
        push!(get!(wire_keys, _portkey(state.to), Int[]), i)
    end
    for (i, state) in enumerate(states)
        (state.valid && state.conn.kind == :bond) || continue
        for ep in (state.from, state.to)
            ep.kind == :power || continue
            key = _portkey(ep)
            haskey(wire_keys, key) || continue
            _connection_diag!(
                b,
                ep;
                code = "E102",
                message = "power port `$(ep.port)` of `$(_owner(ep.path))` is both bonded and wired",
                hint = "use either a bond or a wire node on a power port, not both",
                connection = state.conn.id,
            )
            state.valid = false
            for j in wire_keys[key]
                states[j].valid = false
            end
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Wire nodes
# ---------------------------------------------------------------------------------------

"""    _record_junction_bonds!(b, states)

Turn every valid bond that touches a junction into one `JunctionBond` per junction end
(plan 5.4). A bond between two elements has no junction entry: its two equations are
emitted directly. A bond between two junctions gets two virtual bond variables (one `e`,
one `f`) because there is no port that could carry them."""
function _record_junction_bonds!(b::Builder, states::Vector{ConnState})
    for state in states
        (state.valid && state.conn.kind == :bond) || continue
        f = state.from
        t = state.to
        (f.kind == :junction || t.kind == :junction) || continue
        if f.kind == :junction && t.kind == :junction
            eid = state.conn.id * ".e"
            fid = state.conn.id * ".f"
            r = _placeholder_range()
            for (id, field) in ((eid, :e), (fid, :f))
                _add_var!(
                    b,
                    Flat.FlatVar(
                        id,
                        :port,
                        :Real,
                        field === :e ? BGSim.Units.effort_dims(:Generic) :
                        BGSim.Units.flow_dims(:Generic),
                        nothing,
                        Dict{Symbol,Any}(),
                        Flat.Origin(; path = f.path, node = f.node,
                            connection = state.conn.id, kind = :bond),
                    ),
                )
            end
            from_j = _junction(b, f)
            to_j = _junction(b, t)
            from_j === nothing || push!(
                from_j.bonds,
                Flat.JunctionBond(state.conn.id, t.node, t.path, nothing, false, false,
                    String[eid], String[fid]),
            )
            to_j === nothing || push!(
                to_j.bonds,
                Flat.JunctionBond(state.conn.id, f.node, f.path, nothing, true, false,
                    String[eid], String[fid]),
            )
            continue
        end
        port_ep = f.kind == :power ? f : t
        junction_ep = f.kind == :junction ? f : t
        port = get(b.port_at, _portkey(port_ep), nothing)
        port === nothing && continue
        port.size == 1 || continue
        junction = _junction(b, junction_ep)
        junction === nothing && continue
        into = t.kind == :junction
        push!(
            junction.bonds,
            Flat.JunctionBond(
                state.conn.id,
                port_ep.node,
                port_ep.path,
                port_ep.port,
                into,
                into,
                copy(port.eids),
                copy(port.fids),
            ),
        )
    end
    return nothing
end

function _junction(b::Builder, ep::RawEndpoint)
    idx = get(b.junction_by_path, ep.path, 0)
    return idx == 0 ? nothing : b.junctions[idx]
end

function _build_wire_groups!(states::Vector{ConnState})
    uf = UnionFind()
    for state in states
        (state.valid && state.conn.kind == :wire) || continue
        a = _portkey(state.from)
        b = _portkey(state.to)
        _uf_push!(uf, a)
        _uf_push!(uf, b)
        _uf_union!(uf, a, b)
    end
    groups = WireGroup[]
    by_root = Dict{Tuple{String,Symbol},Int}()
    for (i, state) in enumerate(states)
        (state.valid && state.conn.kind == :wire) || continue
        root = _uf_find!(uf, _portkey(state.from))
        idx = get(by_root, root, 0)
        if idx == 0
            push!(groups, WireGroup(Tuple{String,Symbol}[], Int[], :Generic, true))
            idx = length(groups)
            by_root[root] = idx
        end
        g = groups[idx]
        for ep in (state.from, state.to)
            key = _portkey(ep)
            key in g.ports || push!(g.ports, key)
        end
        push!(g.edges, i)
    end
    wire_of_conn = Dict{Int,Int}()
    for (gi, g) in enumerate(groups), ci in g.edges
        wire_of_conn[ci] = gi
    end
    return groups, wire_of_conn
end

# ---------------------------------------------------------------------------------------
# Equation emission (after domain adoption)
# ---------------------------------------------------------------------------------------

"""    across_field(domain) / through_field(domain) -> Symbol

Decision D8: Electrical and Hydraulic have `e` as the across variable and `f` as the
through variable; Translation, Rotation and Planar have `f` across and `e` through."""
function across_field(domain::Symbol)
    return domain in (:Translation, :Rotation, :Planar, :Spatial) ? :f : :e
end

through_field(domain::Symbol) = across_field(domain) === :e ? :f : :e

_placeholder_range() = BGSim.SourceRange("", 0, 0, 0, 0)

"""    port_field_exprs(port, field) -> Vector{Expr}

The scalar expressions of one field (`:e` or `:f`) of a port, one per component. A scalar
port keeps the structured `Field(Name(qname), field)` so the causality pass can recognise
it; a multi-component port uses one qualified `Name` per component."""
function port_field_exprs(port::PortInfo, field::Symbol)
    ids = field === :e ? port.eids : port.fids
    if port.size == 1
        r = port.range
        return BGSim.Expr[Field(Name(Symbol(port.qname), r), field, r)]
    end
    r = _placeholder_range()
    return BGSim.Expr[Name(Symbol(id), r) for id in ids]
end

function _junction_bond_exprs(b::Builder, bond::Flat.JunctionBond)
    eids = BGSim.Expr[Name(Symbol(id), _placeholder_range()) for id in bond.eids]
    fids = BGSim.Expr[Name(Symbol(id), _placeholder_range()) for id in bond.fids]
    if bond.flip
        r = _placeholder_range()
        fids = BGSim.Expr[UnOp(:-, f, r) for f in fids]
    end
    return eids, fids
end

function _wire_origin(b::Builder, group::WireGroup)
    first = group.ports[1]
    path, port = first
    st = get(b.state_by_path, path, nothing)
    conn_id = isempty(group.edges) ? nothing : b.raw[group.edges[1]].conn.id
    return Flat.Origin(; path = path, block = st === nothing ? nothing : st.ref,
        node = st === nothing ? nothing : st.node, connection = conn_id, kind = :wire)
end

function emit_wire_equations!(b::Builder, plan::ConnPlan)
    for group in plan.wires
        group.valid || continue
        length(group.ports) >= 2 || continue
        across = across_field(group.domain)
        through = through_field(group.domain)
        ref_path, ref_name = group.ports[1]
        ref_port = get(b.port_at, (ref_path, ref_name), nothing)
        ref_port === nothing && continue
        ref_across = port_field_exprs(ref_port, across)
        ref_through = port_field_exprs(ref_port, through)
        origin = _wire_origin(b, group)
        for key in group.ports[2:end]
            other = get(b.port_at, key, nothing)
            other === nothing && continue
            other_across = port_field_exprs(other, across)
            other_through = port_field_exprs(other, through)
            for k in eachindex(ref_across)
                k <= length(other_across) || continue
                push!(b.equations, Flat.FlatEq(other_across[k], ref_across[k], origin))
            end
        end
        for k in eachindex(ref_through)
            terms = BGSim.Expr[]
            for key in group.ports
                port = get(b.port_at, key, nothing)
                port === nothing && continue
                exprs = port_field_exprs(port, through)
                k <= length(exprs) || continue
                push!(terms, exprs[k])
            end
            push!(
                b.equations,
                Flat.FlatEq(_sum_exprs(terms, _placeholder_range()), Lit(0.0, _placeholder_range()), origin),
            )
        end
    end
    return nothing
end

function emit_bond_equations!(b::Builder, plan::ConnPlan)
    for state in plan.states
        (state.valid && state.conn.kind == :bond) || continue
        state.from.kind == :junction && continue
        state.to.kind == :junction && continue
        pf = get(b.port_at, _portkey(state.from), nothing)
        pt = get(b.port_at, _portkey(state.to), nothing)
        (pf === nothing || pt === nothing) && continue
        pf.size == pt.size || continue
        origin = Flat.Origin(; path = state.to.path,
            block = _endpoint_block(b, state.to), node = state.to.node,
            connection = state.conn.id, kind = :bond)
        for k in 1:pf.size
            fe = port_field_exprs(pf, :e)[k]
            te = port_field_exprs(pt, :e)[k]
            ff = port_field_exprs(pf, :f)[k]
            tf = port_field_exprs(pt, :f)[k]
            push!(b.equations, Flat.FlatEq(te, fe, origin))
            push!(
                b.equations,
                Flat.FlatEq(tf, UnOp(:-, ff, _placeholder_range()), origin),
            )
        end
    end
    return nothing
end

function emit_signal_equations!(b::Builder, plan::ConnPlan)
    for state in plan.states
        (state.valid && state.conn.kind == :signal) || continue
        from_st = get(b.state_by_path, state.from.path, nothing)
        to_st = get(b.state_by_path, state.to.path, nothing)
        (from_st === nothing || to_st === nothing) && continue
        from_ids = get(from_st.ids, something(state.from.port, Symbol("")), String[])
        to_ids = get(to_st.ids, something(state.to.port, Symbol("")), String[])
        (isempty(from_ids) || length(from_ids) != length(to_ids)) && continue
        origin = Flat.Origin(; path = state.to.path, block = to_st.ref,
            node = state.to.node, connection = state.conn.id, kind = :signal)
        r = _placeholder_range()
        factor = state.factor
        for k in eachindex(to_ids)
            out_expr = Name(Symbol(from_ids[k]), r)
            rhs = factor == 1.0 ? out_expr :
                  BinOp(:*, Lit(factor, r), out_expr, r)
            push!(b.equations, Flat.FlatEq(Name(Symbol(to_ids[k]), r), rhs, origin))
        end
    end
    return nothing
end

function emit_connections!(b::Builder, plan::ConnPlan)
    emit_wire_equations!(b, plan)
    emit_bond_equations!(b, plan)
    emit_signal_equations!(b, plan)
    return nothing
end

# ---------------------------------------------------------------------------------------
# Editor metadata and unconnected ports
# ---------------------------------------------------------------------------------------

function connection_infos(plan::ConnPlan)
    out = Flat.ConnectionInfo[]
    for state in plan.states
        c = state.conn
        factor = if c.kind == :signal
            state.factor == 1.0 ? nothing : state.factor
        else
            state.factor
        end
        push!(
            out,
            Flat.ConnectionInfo(
                c.id,
                c.kind,
                state.from.node,
                state.from.path,
                state.from.port,
                state.to.node,
                state.to.path,
                state.to.port,
                state.domain,
                factor,
            ),
        )
    end
    return out
end

"""    _external_face_use(r, key, path) -> Bool

Whether a raw connection is an *outside* use of the composite face whose internal port key is
`key`. Connections emitted while expanding the composite have `r.diagram == path` (the
composite's own prefix) or a deeper prefix; everything else is a connection of the enclosing
diagram and therefore connects the face."""
function _external_face_use(r::RawConnection, key::Tuple{String,Symbol}, path::String)
    (r.diagram == path || startswith(r.diagram, path * "/")) && return false
    return _portkey(r.from) == key || _portkey(r.to) == key
end

"""    check_unconnected!(b, plan)

Plan 5.2.6: an input that no signal connection drives is E101, and so is a power port that
no bond or wire attaches to, with the hint that names the sources. An output may stay
unconnected. A junction without a bond is E101 too: it has no variables and no equations,
so it can never be part of a solvable system. A connection that was *attempted* but
invalid does not produce this second diagnostic (the E102 already points at the problem)."""
function check_unconnected!(b::Builder, plan::ConnPlan)
    for st in b.states
        for (name, port) in st.ports
            haskey(plan.attempts, _portkey(st.path, name)) && continue
            _report!(
                b,
                st;
                code = "E101",
                message = "power port `$name` of `$(st.path)` is not connected",
                hint = "connect it or add a source (Se/Sf, Fixed, Ground)",
                range = port.range,
            )
        end
        for d in BGSim.declarations(st.pb, :inputs)
            name = BGSim.decl_name(d)
            haskey(plan.input_attempts, _portkey(st.path, name)) && continue
            _report!(
                b,
                st;
                code = "E101",
                message = "input `$name` of `$(st.path)` is not connected",
                hint = "connect it or add a source (Se/Sf, Fixed, Ground)",
                range = BGSim.decl_range(d),
                scope = "@inputs",
            )
        end
    end
    # A textual composite's interface port is not a variable of its own: it is a face on an
    # internal component port. The face must still be used by a connection *outside* the
    # composite. Internal wiring is in `r.diagram == path` (or a prefix of it), so only the
    # remaining connections count. An output may stay unconnected, like a block output.
    for (path, faces) in b.boundary
        node_id = get(b.boundary_nodes, path, nothing)
        for (name, ep) in faces
            sp = get(b.boundary_ports, (path, name), nothing)
            sp === nothing && continue
            sp.kind == :signal && sp.direction == :output && continue
            key = _portkey(ep)
            any(r -> _external_face_use(r, key, path), b.raw) && continue
            what = sp.kind == :power ? "power port" : "input"
            push!(
                b.diagnostics,
                diag(
                    "E101",
                    "$what `$name` of `$path` is not connected";
                    hint = "connect it or add a source (Se/Sf, Fixed, Ground)",
                    path = path,
                    node = node_id,
                ),
            )
        end
    end
    for junction in b.junctions
        isempty(junction.bonds) || continue
        push!(
            b.diagnostics,
            diag(
                "E101",
                "junction `$(junction.path)` has no connections";
                hint = "connect at least one bond to the junction",
                path = junction.path,
                node = junction.node,
            ),
        )
    end
    return nothing
end
