# Junction equations (plan 5.4).
#
# A 0- or 1-junction has no variables of its own: each bond carries `(e_b, f_b)`, which is
# the attached port's own effort/flow pair (or a virtual pair for a junction-to-junction
# bond). With `n` bonds and `s_i = +1` when bond `i` points into the junction and `-1`
# otherwise (plan 5.4):
#
# * 0-junction: all `e_b` equal (`n-1` equations), and `S s_i f_b,i = 0`;
# * 1-junction: all `f_b` equal (`n-1` equations), and `S s_i e_b,i = 0`.
#
# That is exactly `n` equations, which is what the balance accounting expects: each attached
# port contributed one "port unknown" to its block, and the junction supplies the matching
# equation. Bond orientation enters through `JunctionBond.flip` (plan 5.5: `X.f = -f_b` when
# the port sits at the `from` end).
#
# The junction width (the number of components) is the adopted domain's size: scalar domains
# give 1, `Planar` 3 and `Spatial` 6. A junction-to-junction bond creates its virtual `(e, f)`
# pair per component once that width is known. A `Generic` scalar port attached to a
# multibond junction is E102, not a silently dropped junction (which would surface as an
# unrelated E103).

"""    _junction_width(plan, junction) -> Union{Int,Nothing}

The junction's component count from domain adoption, or `nothing` when no domain was
adopted (which the caller reports as E102 instead of dropping the junction)."""
function _junction_width(plan::ConnPlan, junction::Flat.JunctionInfo)
    adopted = get(plan.port_domains, _junction_key(junction.path), nothing)
    return adopted === nothing ? nothing : domain_size(adopted)
end

function _junction_width_error!(
    b::Builder,
    junction::Flat.JunctionInfo,
    bond::Flat.JunctionBond,
    message::AbstractString,
)
    push!(
        b.diagnostics,
        diag(
            "E102",
            message;
            hint = "a multibond junction carries every component of one domain; give the port the same domain (Power{Planar}/Power{Spatial}) or use a converter",
            path = junction.path,
            node = junction.node,
            connection = bond.connection,
        ),
    )
    return nothing
end

"""Create the virtual `(e, f)` pair of a junction-to-junction bond at the junction width.

A scalar width keeps the historical `conn.e`/`conn.f` ids; a multibond width uses
`conn.e[k]`/`conn.f[k]`, one variable per component."""
function _junction_virtual_vars!(
    b::Builder,
    junction::Flat.JunctionInfo,
    index::Int,
    width::Int,
    domain::Symbol,
)
    bond = junction.bonds[index]
    isempty(bond.eids) || return bond
    suffix(k) = width == 1 ? "" : "[" * string(k) * "]"
    eids = String[bond.connection * ".e" * suffix(k) for k in 1:width]
    fids = String[bond.connection * ".f" * suffix(k) for k in 1:width]
    for (ids, field) in ((eids, :e), (fids, :f))
        for (k, id) in enumerate(ids)
            unit = field === :e ? BGSim.Units.effort_dims(domain, k) :
                   BGSim.Units.flow_dims(domain, k)
            _add_var!(
                b,
                Flat.FlatVar(
                    id,
                    :port,
                    :Real,
                    unit,
                    nothing,
                    Dict{Symbol,Any}(),
                    Flat.Origin(; path = junction.path, node = junction.node,
                        connection = bond.connection, kind = :bond),
                ),
            )
        end
    end
    updated = Flat.JunctionBond(
        bond.connection,
        bond.node,
        bond.path,
        bond.port,
        bond.into,
        bond.flip,
        eids,
        fids,
    )
    junction.bonds[index] = updated
    return updated
end

function emit_junction_equations!(b::Builder, plan::ConnPlan)
    r = _placeholder_range()
    for junction in b.junctions
        isempty(junction.bonds) && continue
        width = _junction_width(plan, junction)
        if width === nothing
            # When the junction's island already failed domain adoption (for example two
            # concrete domains), its bond E102 is the error; do not add a redundant one.
            # If the bonds are still valid and no domain was adopted, the width really is
            # ambiguous and must not be dropped silently.
            any(
                bond -> any(state -> state.conn.id == bond.connection && state.valid,
                    plan.states),
                junction.bonds,
            ) || continue
            push!(
                b.diagnostics,
                diag(
                    "E102",
                    "junction `$(junction.path)` has no adopted power domain, so its width is ambiguous",
                    hint = "connect the junction to a concrete-domain port (or a Generic bond graph element)",
                    path = junction.path,
                    node = junction.node,
                ),
            )
            continue
        end
        adopted = get(plan.port_domains, _junction_key(junction.path), :Generic)
        valid = true
        for bond in junction.bonds
            bond.port === nothing && continue
            port = get(b.port_at, (bond.path, bond.port), nothing)
            if port === nothing
                valid = false
                continue
            end
            if port.domain == :Generic && width > 1
                _junction_width_error!(
                    b,
                    junction,
                    bond,
                    "a Generic scalar port cannot join a $(adopted) multibond: port `$(port.name)` of `$(_owner(bond.path))` is scalar but junction `$(junction.path)` has $(width) components",
                )
                valid = false
            elseif port.size != width
                _junction_width_error!(
                    b,
                    junction,
                    bond,
                    "port `$(port.name)` of `$(_owner(bond.path))` has $(port.size) component(s) but junction `$(junction.path)` adopted $(adopted) ($(width))",
                )
                valid = false
            end
        end
        valid || continue
        for index in eachindex(junction.bonds)
            _junction_virtual_vars!(b, junction, index, width, adopted)
        end
        exprs = Tuple{Vector{BGSim.Expr},Vector{BGSim.Expr}}[]
        for bond in junction.bonds
            push!(exprs, _junction_bond_exprs(b, bond))
        end
        size = length(exprs[1][1])
        all(length(e) == size for (e, _) in exprs) || continue
        origin = Flat.Origin(; path = junction.path, node = junction.node,
            kind = :junction)
        if junction.kind == 0
            for k in 2:length(exprs)
                for c in 1:size
                    push!(b.equations, Flat.FlatEq(exprs[k][1][c], exprs[1][1][c], origin))
                end
            end
            for c in 1:size
                terms = BGSim.Expr[]
                for (i, (_, f)) in enumerate(exprs)
                    signed = junction.bonds[i].into ? f[c] : UnOp(:-, f[c], r)
                    push!(terms, signed)
                end
                push!(
                    b.equations,
                    Flat.FlatEq(_sum_exprs(terms, r), Lit(0.0, r), origin),
                )
            end
        else
            for k in 2:length(exprs)
                for c in 1:size
                    push!(b.equations, Flat.FlatEq(exprs[k][2][c], exprs[1][2][c], origin))
                end
            end
            for c in 1:size
                terms = BGSim.Expr[]
                for (i, (e, _)) in enumerate(exprs)
                    signed = junction.bonds[i].into ? e[c] : UnOp(:-, e[c], r)
                    push!(terms, signed)
                end
                push!(
                    b.equations,
                    Flat.FlatEq(_sum_exprs(terms, r), Lit(0.0, r), origin),
                )
            end
        end
    end
    return nothing
end
