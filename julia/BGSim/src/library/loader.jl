# The library loader: parse + check a block source once per (source hash, ref, path) and
# turn it into a `BlockDef`; discover the stdlib and a project library on disk.
#
# The cache is an in-memory `Dict` guarded by a `ReentrantLock` (the worker handles requests
# on several Julia tasks). It holds the fully checked `BlockDef`, so a repeated load of the
# same text does no parsing and no checking at all. The bound exists so that a long-running
# worker that is fed many unsaved editor buffers cannot grow without limit; when it is hit,
# the whole cache is dropped (a simple, honest policy — entries are cheap to rebuild).

"""    source_hash(text) -> UInt64

The cache key of a block source: FNV-1a 64 over its UTF-8 bytes. A local 12-line hash is
used instead of `SHA` on purpose: `SHA` is a standard-library package that would have to be
added to `Project.toml`, and the library work package must not change that file while other
work packages run in parallel. FNV-1a is deterministic across processes and versions, which
is all a source cache needs.
"""
function source_hash(text::AbstractString)::UInt64
    h = 0xcbf29ce484222325
    for byte in codeunits(text)
        h = (h ⊻ UInt64(byte)) * 0x00000100000001b3
    end
    return h
end

const _CACHE = Dict{Tuple{UInt64,String,String},BlockDef}()
const _CACHE_LOCK = ReentrantLock()
const CACHE_LIMIT = 512

"""    clear_cache()

Drop every cached block. The catalog is not cached, so this only affects repeated checks of
the same source text (`cache.clear` in the worker protocol)."""
function clear_cache()
    lock(_CACHE_LOCK) do
        empty!(_CACHE)
    end
    return nothing
end

"""    cached_blocks() -> Int

The number of entries in the parse cache (for the tests and for diagnostics)."""
cached_blocks() = lock(_CACHE_LOCK) do
    length(_CACHE)
end

"""    default_group(ref) -> String

The catalog group implied by a block reference: the stdlib directory's human name,
`"Project"` for a project block, `"Inline"` otherwise."""
function default_group(ref::AbstractString)
    prefix = "stdlib:"
    if startswith(ref, prefix)
        body = split(ref[length(prefix)+1:end], '/')
        if length(body) == 2
            g = group_info(body[1])
            g === nothing || return g.name
        end
        return "Standard library"
    end
    startswith(ref, "project:") && return PROJECT_GROUP
    return "Inline"
end

"""
    load_block(text; ref = "inline:x", path = nothing, group = nothing) -> BlockDef

Parse and check one `@block` source and wrap it in a [`BlockDef`](@ref). `ref` is the block
reference used in diagnostics and in the catalog (plan 3.1); `path` is the file it came from
and becomes the source range's file name and the catalog's `path`. `group` defaults to
[`default_group`](@ref)`(ref)`; the description and icon come from [`BLOCK_METADATA`](@ref)
(the empty string for a block that has no entry).

Results are cached by `(source_hash(text), ref, path)`, so loading the same text twice
returns the identical `BlockDef` and does neither parsing nor checking the second time.
"""
function load_block(
    text::AbstractString;
    ref::AbstractString = "inline:x",
    path::Union{Nothing,AbstractString} = nothing,
    group::Union{Nothing,AbstractString} = nothing,
)
    text_s = String(text)
    ref_s = String(ref)
    path_s = path === nothing ? nothing : String(path)
    key = (source_hash(text_s), ref_s, something(path_s, ""))
    cached = lock(_CACHE_LOCK) do
        get(_CACHE, key, nothing)
    end
    cached === nothing || return cached

    pb = parse_block(text_s; filename = something(path_s, ref_s), ref = ref_s)
    diagnostics = sort_diagnostics(check_block(pb))
    meta = block_metadata(ref_s)
    block = BlockDef(
        block_name(pb),
        ref_s,
        group === nothing ? default_group(ref_s) : String(group),
        RELEASE,
        meta === nothing ? "" : meta.description,
        meta === nothing ? "" : meta.icon,
        block_source(pb),
        something(path_s, ""),
        block_interface(pb),
        pb,
        diagnostics,
    )

    lock(_CACHE_LOCK) do
        length(_CACHE) >= CACHE_LIMIT && empty!(_CACHE)
        _CACHE[key] = block
    end
    return block
end

"""
    load_source(text; ref = "inline:x", path = nothing) -> ParsedBlock

Parse and check one block source and return its `ParsedBlock`, exactly as
[`load_block`](@ref) does; this is the front-end shaped entry point of the fast
as-you-type pass. The check diagnostics are not attached to the returned `ParsedBlock` (it
carries the parse-stage ones only): use `load_block(...).diagnostics` when you need them,
or re-run `check_block`, which is pure and cheap for one block.
"""
function load_source(
    text::AbstractString;
    ref::AbstractString = "inline:x",
    path::Union{Nothing,AbstractString} = nothing,
)
    return load_block(text; ref = ref, path = path).ast
end

"""
    stdlib_dir() -> String

The absolute path of `julia/BGSim/stdlib`, the root of the standard library. Its
subdirectories are the catalog groups (see [`GROUPS`](@ref)).
"""
stdlib_dir() = normpath(joinpath(@__DIR__, "..", "..", "stdlib"))

"""
    load_stdlib() -> Vector{BlockDef}

Load every `stdlib/<group>/<Name>.jl` of the groups in [`GROUPS`](@ref), sorted by `ref`.
One `@block` per file, with the file name equal to the block name (plan 3.3); a mismatch is
reported as E001 on that block, pointing at its source, and the block stays in the list so
the editor can show it.

The parse cache makes a repeated call cheap; the files are re-read every time, so an edit
on disk is picked up without a restart.
"""
function load_stdlib()
    root = stdlib_dir()
    blocks = BlockDef[]
    for g in GROUPS
        dir = joinpath(root, g.dir)
        isdir(dir) || continue
        for file in sort(readdir(dir; join = true))
            endswith(file, ".jl") || continue
            stem = splitext(basename(file))[1]
            ref = "stdlib:" * g.dir * "/" * stem
            block = load_block(read(file, String); ref = ref,
                path = "stdlib/" * g.dir * "/" * stem * ".jl", group = g.name)
            push!(blocks, _check_file_name(block, stem))
        end
    end
    sort!(blocks; by = b -> b.ref)
    return blocks
end

"""
    load_project_library(dir) -> Vector{BlockDef}

Load every `library/<Name>.jl` of a project (plan 3.3: one `@block` per file, the file name
equals the block name), sorted by `ref`. The refs are `project:<Name>` and the catalog path
is `library/<Name>.jl`, relative to the project root.

Two project-library rules are reported as E001 on the offending block, pointing at its
source: a file whose name does not match the block name, and a block name declared by more
than one file (a model refers to `project:<Name>`, so that would be ambiguous). A missing
directory yields an empty list — a project simply may not have a library yet.
"""
function load_project_library(dir::AbstractString)
    isdir(dir) || return BlockDef[]
    blocks = BlockDef[]
    declared = Dict{Symbol,String}()
    for file in sort(readdir(dir; join = true))
        endswith(file, ".jl") || continue
        stem = splitext(basename(file))[1]
        block = load_block(read(file, String); ref = "project:" * stem,
            path = "library/" * stem * ".jl", group = PROJECT_GROUP)
        block = _check_file_name(block, stem)
        previous = get(declared, block.name, nothing)
        if previous === nothing
            declared[block.name] = stem
        else
            block = _with_diagnostics(
                block,
                diag(
                    "E001",
                    "the block name `$(block.name)` is already declared in `$previous.jl`",
                    block.ast,
                    block_range(block.ast);
                    hint = "a model refers to `project:$(block.name)`, so a block name must be unique in the project library",
                ),
            )
        end
        push!(blocks, block)
    end
    sort!(blocks; by = b -> b.ref)
    return blocks
end

# ---------------------------------------------------------------------------------------
# Packaging diagnostics
# ---------------------------------------------------------------------------------------

function _with_diagnostics(block::BlockDef, d::Diagnostic)
    diags = sort_diagnostics(vcat(block.diagnostics, d))
    return BlockDef(
        block.name,
        block.ref,
        block.group,
        block.release,
        block.description,
        block.icon,
        block.source,
        block.path,
        block.interface,
        block.ast,
        diags,
    )
end

# Plan 3.3: `library/<BlockName>.jl` with one `@block` whose name is `<BlockName>`.
function _check_file_name(block::BlockDef, stem::String)
    String(block.name) == stem && return block
    return _with_diagnostics(
        block,
        diag(
            "E001",
            "the file name `$stem.jl` does not match the block name `$(block.name)`",
            block.ast,
            block_range(block.ast);
            hint = "the library maps `<Name>.jl` to a block named `<Name>`; rename one of them",
        ),
    )
end
