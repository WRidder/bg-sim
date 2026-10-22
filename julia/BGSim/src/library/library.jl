"""
    Library

The block library of bg-sim (plan section 3.2 and work package J1.3): it loads `@block`
sources from `julia/BGSim/stdlib/` and from a project's `library/` directory, checks them
with the front end, and assembles the catalog that `catalog.get` returns to the editor.

The module is included from `BGSim` and is used as `BGSim.Library.catalog()`. It never
evaluates a block source; parsing and checking go through `parse_block` / `check_block`
(work package J1.1).

# Public API

| function | result |
| --- | --- |
| [`load_block`](@ref)`(text; ref, path, group)` | the checked block as a [`BlockDef`](@ref), cached by source hash |
| [`load_source`](@ref)`(text; ref, path)` | just its `ParsedBlock` |
| [`stdlib_dir`](@ref)`()` | the absolute path of `julia/BGSim/stdlib` |
| [`load_stdlib`](@ref)`()` | every stdlib block as a [`BlockDef`](@ref), sorted by ref |
| [`load_project_library`](@ref)`(dir)` | every `library/<Name>.jl` of a project, sorted by ref |
| [`catalog`](@ref)`(project_dir = nothing)` | the plan 3.2 catalog as JSON-ready `NamedTuple`s |
| [`intrinsics`](@ref)`()` | the D12 intrinsic table (`interp1`, `interp2`, `noise_normal`, `delay`) |
| [`clear_cache`](@ref)`()` | drop the parse cache (`cache.clear`) |

# Block metadata

The language has no syntax for the catalog's presentation fields (`group`, `release`,
`description`, `icon`), so they live in the two tables in `catalog.jl`: the group table maps
a stdlib directory to its human name and icon prefix, and `BLOCK_METADATA` holds the
description and icon of every stdlib block. The test suite asserts that the table covers
exactly the stdlib blocks and that every field matches `contracts/fixtures/catalog`.
"""
module Library

using ..BGSim: ParsedBlock, Diagnostic, diag, sort_diagnostics, parse_block, check_block,
    block_interface, block_name, block_range, block_source, FUNCTION_RULES

# `to_namedtuple` / `to_dict` are extended with a `BlockDef` method, so they must be
# imported (not `using`), which also keeps one JSON-shape vocabulary for diagnostics and
# blocks.
import ..BGSim: to_namedtuple, to_dict

"""
    BlockDef

One parsed, checked library block: the IR type of plan section 5.1, limited to what the
library stage needs. It is immutable and JSON-serialisable through
[`to_namedtuple`](@ref) / [`to_dict`](@ref).

| field | meaning |
| --- | --- |
| `name` | the block name as a `Symbol` (`:C`) |
| `ref` | `stdlib:<group>/<Name>` or `project:<Name>` (plan 3.1) |
| `group` | human-readable group, e.g. `"Bond graph"` |
| `release` | library release the block ships in, `"0.1"` for M1 |
| `description`, `icon` | catalog presentation data |
| `source` | the full `@block ... end` text |
| `path` | `stdlib/<group>/<Name>.jl`, or `library/<Name>.jl` for a project block |
| `interface` | the seven arrays of plan 3.2, as returned by `block_interface` |
| `ast` | the `ParsedBlock` (parse-stage diagnostics only) |
| `diagnostics` | every diagnostic of the parse and check passes, sorted |

`has_errors(b)` is the fast "is this block usable" test; warnings (W204, the block-level
E103 balance precheck) do not make a block unusable.
"""
struct BlockDef
    name::Symbol
    ref::String
    group::String
    release::String
    description::String
    icon::String
    source::String
    path::String
    interface::NamedTuple
    ast::ParsedBlock
    diagnostics::Vector{Diagnostic}
end

"""
    has_errors(b::BlockDef) -> Bool

True when the block's diagnostics contain an error. Warnings do not count: a block with only
W204 (an unused declaration) or the block-level E103 balance warning is still usable.
"""
has_errors(b::BlockDef) = any(d -> d.severity == "error", b.diagnostics)

"""
    to_namedtuple(b::BlockDef) -> NamedTuple

The block in the plan 3.2 catalog shape, with exactly the field names of
`contracts/schemas/catalog.schema.json` and in the schema's order. The seven interface
arrays are passed through unchanged.
"""
function to_namedtuple(b::BlockDef)
    i = b.interface
    return (
        ref = b.ref,
        name = String(b.name),
        group = b.group,
        release = b.release,
        description = b.description,
        icon = b.icon,
        constants = i.constants,
        parameters = i.parameters,
        inputs = i.inputs,
        outputs = i.outputs,
        ports = i.ports,
        variables = i.variables,
        causality = i.causality,
        source = b.source,
        path = b.path,
    )
end

"""
    to_dict(b::BlockDef) -> Dict{String,Any}

The same shape as [`to_namedtuple`](@ref) as a plain `Dict{String,Any}` tree, ready for
`JSON3.write`. Nested `NamedTuple`s and `Symbol`s are converted, so nothing but `Dict`,
`Vector`, `String`, numbers, booleans and `nothing` remains.
"""
to_dict(b::BlockDef) = _dictify(to_namedtuple(b))

_dictify(v::NamedTuple) =
    Dict{String,Any}(String(k) => _dictify(getfield(v, k)) for k in keys(v))
_dictify(v::AbstractVector) = Any[_dictify(x) for x in v]
_dictify(v::AbstractDict) = Dict{String,Any}(String(k) => _dictify(v[k]) for k in keys(v))
_dictify(v::Symbol) = String(v)
_dictify(v) = v

include("catalog.jl")
include("loader.jl")
include("intrinsics.jl")

export BlockDef, has_errors, load_block, load_source, stdlib_dir, load_stdlib,
    load_project_library, catalog, intrinsics, clear_cache

end # module Library
