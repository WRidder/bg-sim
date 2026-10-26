"""
    Units

Unit parsing, dimensions and the block-level unit check (plan section 5.3, decisions D2
and D9). This module is a pure addition to the front end: it reads `ParsedBlock`s through
the public AST accessors and never evaluates user code.

| function | result |
| --- | --- |
| [`parse_unit`](@ref)`(s)` | the [`Dims`](@ref) of a unit string; throws [`UnitParseError`](@ref) |
| [`unit_string`](@ref)`(d)` | the canonical string of a `Dims`, accepted by `parse_unit` |
| [`dims_of`](@ref)`(expr, env)` | the dimension of an expression, or `nothing` for a wildcard |
| [`conversion_factor`](@ref)`(from, to)` | the factor for a same-dimension wire, `nothing` otherwise |
| [`substitute_domain`](@ref)`(d, domain)` | replace `effort`/`flow` by a domain's concrete units |
| [`unit_env`](@ref)`(pb[, domain])` | the name → unit map of a block (declarations, ports, `t`) |
| [`check_units`](@ref)`(pb[, domain])` | E006 diagnostics for one block; called by `check_block` |

Design notes:

* A `Dims` is an integer exponent vector over m, kg, s, A, K, mol, cd plus the
  pseudo-dimensions `effort` and `flow` (D9), and a `Float64` scale. It is a dimension,
  not a value; `mm` is the metre dimension with scale 1e-3.
* The unit string parser handles `*`, `/`, `^` with an integer exponent, parentheses,
  numeric scale factors and whitespace/`·` multiplication (`dims.jl` holds the table,
  `unitparse.jl` the parser).
* Variables and parameters without a `unit` are wildcards — this is not inference (plan
  5.3). A wildcard makes the whole sum or product a wildcard, and `check_units` skips it.
* `effort`/`flow` are substituted as soon as the block has a concrete port domain (D9);
  a `Generic` block keeps them symbolic, which is what makes `c = flow*s/effort` checkable
  before the connection pass (J2.5) adopts the domain. Once the flattener adopts a domain it
  calls `check_units(pb, adopted)` again, with the substituted units and their concrete
  labels.
* E006 is the spec's "unit inconsistency"; a scale-only difference between two units of one
  dimension is E006 too (the language does no runtime conversion).

The module is included from `BGSim` as `BGSim.Units`; `src/syntax/scopes.jl` calls
`check_units` behind an `isdefined` guard, so this file landing is what makes the check
live. `BGSim.check_block` owns the pass order; this module owns nothing outside
`src/units/`.
"""
module Units

include("dims.jl")
include("unitparse.jl")
include("unitcheck.jl")

end # module Units
