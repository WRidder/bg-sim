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

"""    ConnState(conn, from, to, valid, domain, factor, diagram)

One connection with its resolved endpoints. `valid` is cleared by any E102 (or by a domain
conflict found in `domains.jl`); `domain` is the adopted power domain; `factor` is the unit
conversion inserted by the compiler (1.0 when none); `diagram` is the path of the (sub)diagram
the connection belongs to ("" at the root): connection ids are unique only within one diagram."""
mutable struct ConnState
    conn::IR.ModelConnection
    from::RawEndpoint
    to::RawEndpoint
    valid::Bool
    domain::Union{Symbol,Nothing}
    factor::Float64
    diagram::String
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
        state = ConnState(raw.conn, raw.from, raw.to, true, nothing, 1.0, raw.diagram)
        push!(states, state)
        _classify_one!(b, state, i, attempts, bond_attempts, sources)
    end
    _check_port_conflicts!(b, states)
    check_orientations!(b, states)
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
        if bad.path in b.failed_nodes
            # the node's block failed to load and already said why
            state.valid = false
            return nothing
        end
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
        # C-MB1/ADR-MB1: a multibond bond may join two concrete ports of the same multibond
        # domain (the frame rule is what checks such a bond). A scalar bond still needs a
        # Generic port or a junction (D7).
        multibond_pair = pf.domain == pt.domain && pf.domain in (:Planar, :Spatial)
        if !multibond_pair
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
# Port orientation (plan/PORT_ORIENTATION_PLAN.md, O3, O4, O13, O14): E114
# ---------------------------------------------------------------------------------------

"""    OrientationAnchor(owner, port, kind, pair, ref)

One declared orientation that one end of a bond must satisfy. `owner` is the path of the
instance that declares it: the leaf block the end resolves to, or a textual composite whose
face the end passes through. `kind` is `:in`, `:out` or `:through`; `pair` is the other port
of a `through` pair (`nothing` otherwise); `ref` is the declaring block."""
struct OrientationAnchor
    owner::String
    port::Symbol
    kind::Symbol
    pair::Union{Symbol,Nothing}
    ref::String
end

_anchor_label(a::OrientationAnchor) = "`$(a.port)` of `$(_owner(a.owner))`"

function _push_anchor!(out, decls, owner::String, port::Symbol, ref::String)
    for o in decls
        port in BGSim.orientation_ports(o) || continue
        ports = BGSim.orientation_ports(o)
        kind = BGSim.orientation_kind(o)
        pair = kind === :through ? (ports[1] === port ? ports[2] : ports[1]) : nothing
        push!(out, OrientationAnchor(owner, port, kind, pair, ref))
        break   # a port has one orientation; `check_block` reports a second entry (E003)
    end
    return out
end

"""    _orientation_anchors(b, ep) -> Vector{OrientationAnchor}

The declared orientations one bond end must satisfy, as the flattened connection list sees
the end: the `@orientation` entry of the leaf port it resolves to, and that of every textual
composite face it passes through on the way (a composite may declare the orientation of its
own ports). A junction end has none: a model junction, and a composite face that is an
internal junction unless the composite declares an orientation for it. So a bond between two
junctions is never checked (O14)."""
function _orientation_anchors(b::Builder, ep::RawEndpoint)
    out = OrientationAnchor[]
    if ep.kind == :power && ep.port !== nothing
        st = get(b.state_by_path, ep.path, nothing)
        st === nothing || _push_anchor!(out, BGSim.orientation(st.pb), ep.path, ep.port, st.ref)
    end
    if ep.face !== nothing
        for (path, port) in get(b.face_chain, ep.face, Tuple{String,Symbol}[ep.face])
            entry = get(b.composite_orientation, path, nothing)
            entry === nothing && continue
            _push_anchor!(out, entry[2], path, port, entry[1])
        end
    end
    return out
end

# What the user sees at one end of a bond: the face for an end reached through a subsystem
# or composite port, the instance port or junction otherwise.
function _orientation_end_label(ep::RawEndpoint)
    ep.face === nothing && return _endpoint_label(ep)
    return "`$(ep.face[2])` of `$(_owner(ep.face[1]))`"
end

# "`p` of `C1` is declared `in`", naming the exposing face when the declaration sits on an
# internal port.
function _anchor_text(a::OrientationAnchor, ep::RawEndpoint)
    shown = ep.face === nothing ? (ep.path, ep.port) : ep.face
    (a.owner, a.port) == shown && return "$(_anchor_label(a)) is declared `$(a.kind)`"
    return "$(_anchor_label(a)), which $(_orientation_end_label(ep)) exposes, is declared `$(a.kind)`"
end

_composite_source(b::Builder, state::ConnState) =
    get(b.conn_source, (state.diagram, state.conn.id), nothing)

function _bond_label(b::Builder, state::ConnState)
    src = _composite_source(b, state)
    src === nothing && return "bond `$(state.conn.id)`"
    return "bond `connect($(src.from_text), $(src.to_text))` of `$(_owner(state.diagram))`"
end

function _reverse_hint(b::Builder, state::ConnState)
    src = _composite_source(b, state)
    src === nothing && return "reverse bond `$(state.conn.id)`, so that it runs from " *
                              "$(_orientation_end_label(state.to)) to $(_orientation_end_label(state.from))"
    return "reverse the bond: write `connect($(src.to_text), $(src.from_text))`"
end

# One E114. A bond inside a textual composite points at its `connect` line and the composite's
# node; a bond reaching a face is reported on the subsystem or composite node the user sees.
function _orientation_diag!(b::Builder, state::ConnState, ep::RawEndpoint; message, hint)
    src = _composite_source(b, state)
    if src !== nothing
        push!(
            b.diagnostics,
            diag(
                "E114",
                message;
                hint = hint,
                path = isempty(state.diagram) ? nothing : state.diagram,
                block = src.ref,
                scope = "@connections",
                source = SourceRef(source_kind(src.ref), src.ref, src.range),
                node = src.node,
                connection = state.conn.id,
            ),
        )
        return nothing
    end
    if ep.face !== nothing
        path = ep.face[1]
        node = get(b.boundary_nodes, path, ep.node)
        entry = get(b.composite_orientation, path, nothing)
        block = entry === nothing ? nothing : entry[1]
    else
        path, node, block = ep.path, ep.node, _endpoint_block(b, ep)
    end
    push!(
        b.diagnostics,
        diag(
            "E114",
            message;
            hint = hint,
            path = isempty(path) ? nothing : path,
            block = block,
            node = isempty(node) ? nothing : node,
            connection = state.conn.id,
        ),
    )
    return nothing
end

"""    check_orientations!(b, states)

E114, the bond-direction rule of the declared port orientations (O3, O4, O13):

- the end of a bond at an `in` port is the bond's head (`to`), and the end at an `out` port
  its tail (`from`); a violating bond is reported once, with the hint to reverse it;
- a bond between two `in` or two `out` ports cannot be fixed by reversing it: the hint is to
  put a junction in between;
- of the two bonds at a `(a, b) => :through` pair, one arrives and the other leaves. One bonded
  port alone is never an error.

Only valid bonds are checked; wires and signal connections have no direction. An end is
checked against the port it finally reaches through subsystem and composite faces (and any
orientation a composite declares on a face it passes), so composite `@connections` are
checked like diagram bonds. The bond stays in the model: E114 is an error, but it does not
cascade into balance or causality diagnostics."""
function check_orientations!(b::Builder, states::Vector{ConnState})
    through_ends = Dict{Tuple{String,Symbol},Vector{Tuple{Int,Symbol}}}()
    pairs = Set{Tuple{String,Symbol,Symbol}}()
    for (i, state) in enumerate(states)
        (state.valid && state.conn.kind == :bond) || continue
        ends = ((state.from, :tail), (state.to, :head))
        anchors = [_orientation_anchors(b, ep) for (ep, _) in ends]
        violated = Tuple{OrientationAnchor,RawEndpoint}[]
        for (k, (ep, role)) in enumerate(ends)
            for a in anchors[k]
                if a.kind === :through
                    push!(get!(through_ends, (a.owner, a.port), Tuple{Int,Symbol}[]), (i, role))
                    key = String(a.port) < String(a.pair) ? (a.owner, a.port, a.pair) :
                          (a.owner, a.pair, a.port)
                    push!(pairs, key)
                elseif (a.kind === :in && role !== :head) || (a.kind === :out && role !== :tail)
                    push!(violated, (a, ep))
                end
            end
        end
        isempty(violated) && continue
        fixed(k) = [a for a in anchors[k] if a.kind === :in || a.kind === :out]
        same = intersect(Set(a.kind for a in fixed(1)), Set(a.kind for a in fixed(2)))
        bond = _bond_label(b, state)
        if !isempty(same)
            # O4: two fixed ports of one kind; no direction satisfies both.
            kind = :in in same ? :in : :out
            a1 = first(a for a in fixed(1) if a.kind === kind)
            a2 = first(a for a in fixed(2) if a.kind === kind)
            _orientation_diag!(
                b, state, last(first(v for v in violated if v[1].kind === kind));
                message = "$bond joins two `$kind` ports, $(_anchor_label(a1)) and " *
                          "$(_anchor_label(a2)): no direction of the bond satisfies both",
                hint = kind === :in ?
                       "put a junction in between, with a bond from the junction to each `in` port" :
                       "put a junction in between, with a bond from each `out` port to the junction",
            )
            continue
        end
        parts = [_anchor_text(a, ep) for (a, ep) in violated]
        rule = if all(v -> v[1].kind === :in, violated)
            "a bond must end at an `in` port"
        elseif all(v -> v[1].kind === :out, violated)
            "a bond must start at an `out` port"
        else
            "the bond must run from the `out` port to the `in` port"
        end
        _orientation_diag!(
            b, state, last(first(violated));
            message = "$bond runs from $(_orientation_end_label(state.from)) to " *
                      "$(_orientation_end_label(state.to)), but $(join(parts, " and ")): $rule",
            hint = _reverse_hint(b, state),
        )
    end
    for key in sort!(collect(pairs))
        _check_through_pair!(b, states, key, through_ends)
    end
    return nothing
end

# O13: the two bonds of a `through` pair have opposite directions relative to the block.
function _check_through_pair!(b::Builder, states, key, through_ends)
    owner, p, q = key
    at_p = get(through_ends, (owner, p), Tuple{Int,Symbol}[])
    at_q = get(through_ends, (owner, q), Tuple{Int,Symbol}[])
    (length(at_p) == 1 && length(at_q) == 1) || return nothing
    (i, rp), (j, rq) = at_p[1], at_q[1]
    (i == j || rp !== rq) && return nothing
    sp, sq = states[i], states[j]
    # The bond at q's end is the one reported; its end at the block carries the location.
    ep_q = rq === :head ? sq.to : sq.from
    verb = rp === :head ? "arrive at" : "leave"
    # Suggest a bond whose other end is free: reversing it fixes the pair without breaking an
    # `in`/`out` port elsewhere.
    free(state, role) = all(
        x -> x.kind === :through,
        _orientation_anchors(b, role === :head ? state.from : state.to),
    )
    hint = if free(sq, rq)
        _reverse_hint(b, sq)
    elseif free(sp, rp)
        _reverse_hint(b, sp)
    else
        "neither bond can be reversed, because the other end of each is a fixed `in` or `out` " *
        "port: put a junction between `$(_owner(owner))` and one of them"
    end
    _orientation_diag!(
        b, sq, ep_q;
        message = "$(_bond_label(b, sp)) and $(_bond_label(b, sq)) both $verb `$(_owner(owner))` " *
                  "at `$p` and `$q`, but the `through` pair (`$p`, `$q`) needs one bond to arrive and the other to leave",
        hint = hint,
    )
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
            # The virtual `(e, f)` pair is sized by the adopted junction domain, which is not
            # known until domain adoption; `emit_junction_equations!` creates it per
            # component then (so two Planar junctions are connected component-wise).
            from_j = _junction(b, f)
            to_j = _junction(b, t)
            from_j === nothing || push!(
                from_j.bonds,
                Flat.JunctionBond(state.conn.id, t.node, t.path, nothing, false, false,
                    String[], String[], state.diagram),
            )
            to_j === nothing || push!(
                to_j.bonds,
                Flat.JunctionBond(state.conn.id, f.node, f.path, nothing, true, false,
                    String[], String[], state.diagram),
            )
            continue
        end
        port_ep = f.kind == :power ? f : t
        junction_ep = f.kind == :junction ? f : t
        port = get(b.port_at, _portkey(port_ep), nothing)
        port === nothing && continue
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

Decision D8: Electrical, Hydraulic and Thermal have `e` as the across variable and `f` as
the through variable; Translation, Rotation and Planar have `f` across and `e` through.
Thermal is a pseudo bond domain: `e` is the temperature, `f` the heat flow."""
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
            # A power face that *is* an internal junction (the body port of a RigidBody or a
            # FlexibleBeam end) may stay open: the junction's own equation over its internal
            # bonds sets the outside wrench to zero, i.e. nothing is attached there (a free
            # end). Its internal bonds keep the junction from being empty.
            sp.kind == :power && ep.kind == :junction && continue
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
