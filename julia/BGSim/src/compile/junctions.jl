# Junction equations (plan 5.4).
#
# A 0- or 1-junction has no variables of its own: each bond carries `(e_b, f_b)`, which is
# the attached port's own effort/flow pair (or a virtual pair for a junction-to-junction
# bond). With `n` bonds and `s_i = +1` when bond `i` points into the junction and `-1`
# otherwise (plan 5.4):
#
# * 0-junction: all `e_b` equal (`n-1` equations), and `Σ s_i f_b,i = 0`;
# * 1-junction: all `f_b` equal (`n-1` equations), and `Σ s_i e_b,i = 0`.
#
# That is exactly `n` equations, which is what the balance accounting expects: each attached
# port contributed one "port unknown" to its block, and the junction supplies the matching
# equation. Bond orientation enters through `JunctionBond.flip` (plan 5.5: `X.f = -f_b` when
# the port sits at the `from` end).

function emit_junction_equations!(b::Builder)
    r = _placeholder_range()
    for junction in b.junctions
        isempty(junction.bonds) && continue
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
