# The D12 intrinsic table. Intrinsics are the whitelisted functions that do not lower to an
# expression: they are registered with Symbolics as opaque functions and evaluated by the
# simulator (a table lookup, a seeded noise source, a delay line). Their *availability* is
# already encoded in the one whitelist table (`FUNCTION_RULES` in `src/syntax/whitelist.jl`),
# so this file only adds the presentation text and a stable, JSON-friendly shape; it never
# restates a rule. That way `block.check` and the catalog cannot disagree.

"""
    INTRINSIC_DESCRIPTIONS

One sentence per intrinsic, for the editor's function reference and for the lowering stage's
documentation. The list of intrinsics itself is derived from the whitelist; this table only
describes them.
"""
const INTRINSIC_DESCRIPTIONS = Dict{Symbol,String}(
    :interp1 => "Piecewise-linear 1-D lookup table; lowered to an opaque function.",
    :interp2 => "Bilinear 2-D lookup table; lowered to an opaque function.",
    :noise_normal => "Seeded normal noise sample on the discrete clock; lowered to an opaque function.",
    :delay => "Transport delay by a constant time; lowered to an opaque function with a history buffer (M2, experimental).",
)

"""
    intrinsics() -> Vector{NamedTuple}

The D12 intrinsic table, sorted by name. Each entry is

    (name = "interp1", arity = 3, stdlib_only = false, lowering = :intrinsic,
     description = "...")

where `arity` is the exact number of arguments (every M1 intrinsic has a fixed arity),
`stdlib_only` is the whitelist's flag (plan D12: `interp1` and `interp2` are also available
to users, `noise_normal` and `delay` only inside `stdlib/` blocks) and `lowering` is the
whitelist's lowering tag (`:intrinsic`, or `:delay` for the transport delay).
"""
function intrinsics()
    selected = [rule for rule in FUNCTION_RULES if rule.lowering in (:intrinsic, :delay)]
    rows = [
        (
            name = String(name),
            arity = rule.min_args,
            stdlib_only = rule.stdlib_only,
            lowering = rule.lowering,
            description = get(INTRINSIC_DESCRIPTIONS, name, ""),
        ) for rule in selected for name in rule.names
    ]
    sort!(rows; by = row -> row.name)
    return rows
end
