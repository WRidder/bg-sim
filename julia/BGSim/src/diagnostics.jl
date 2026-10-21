# Diagnostics: the one shape every pass in the worker reports (plan section 3.4).
#
# The JSON contract lives in `contracts/schemas/diagnostic.schema.json`; the sample fixture
# `contracts/fixtures/diagnostic/valid/diagnostics.sample.json` is asserted by
# `test/test_syntax.jl`. `severity` is normally derived from the code by `severity_of`, so no
# call site can invent an inconsistent severity. The single documented exception is the
# block-level balance precheck (E103), which plan section 4.4 wants *reported as a warning*
# when a block is checked on its own; that call site passes `severity = "warning"`.

"""
    SourceRange(file, line, col, endLine, endCol)

A half-open-friendly source range in a user's source file. `line`/`col` are 1-based; `col`
counts characters, not bytes. The JSON contract (plan 3.4) carries only the four numbers;
`file` is filled from the block ref when a range is serialised.
"""
struct SourceRange
    file::String
    line::Int
    col::Int
    endLine::Int
    endCol::Int
end

SourceRange(line::Integer, col::Integer, endLine::Integer, endCol::Integer) =
    SourceRange("", Int(line), Int(col), Int(endLine), Int(endCol))

"""    source_range(x) -> SourceRange

The range of an AST node, declaration, equation or diagnostic. Every node kind implements
this; it is the generic spelling used by the checker and by `diag`."""
source_range(r::SourceRange) = r

function Base.show(io::IO, r::SourceRange)
    if isempty(r.file)
        print(io, r.line, ":", r.col)
    else
        print(io, r.file, ":", r.line, ":", r.col)
    end
    if (r.endLine, r.endCol) != (r.line, r.col)
        print(io, "-", r.endLine, ":", r.endCol)
    end
end

"""
    SourceRef(kind, ref, range)

Where a source-level diagnostic points: the block reference or file, its kind
(`"stdlib"`, `"project"` or `"inline"`) and the range.
"""
struct SourceRef
    kind::String
    ref::String
    range::Union{SourceRange,Nothing}
end

"""    Related(path, message)

A secondary location or fact attached to a diagnostic (for example "balanced" on another
block of an unbalanced system)."""
struct Related
    path::Union{String,Nothing}
    message::String
end

Related(message::AbstractString) = Related(nothing, String(message))

"""
    Diagnostic(code, severity, message, ...)

One diagnostic in the contract shape of plan section 3.4. Build it with [`diag`] rather
than the positional constructor so that `severity` stays derived and the optional fields
stay optional.
"""
struct Diagnostic
    code::String
    severity::String
    message::String
    hint::Union{String,Nothing}
    path::Union{String,Nothing}
    block::Union{String,Nothing}
    scope::Union{String,Nothing}
    source::Union{SourceRef,Nothing}
    node::Union{String,Nothing}
    connection::Union{String,Nothing}
    related::Vector{Related}
end

"""
    severity_of(code) -> String

The one severity table: `E*` is `"error"`, `W*` is `"warning"`, anything else is `"info"`.
"""
function severity_of(code::AbstractString)::String
    isempty(code) && return "info"
    first_char = code[1]
    first_char == 'E' && return "error"
    first_char == 'W' && return "warning"
    return "info"
end

_optstr(::Nothing) = nothing
_optstr(s::AbstractString) = String(s)
_optstr(s::Symbol) = String(s)

"""
    diag(code, message; hint, path, block, scope, source, node, connection, related,
         severity) -> Diagnostic

Build a [`Diagnostic`]. `severity` defaults to `severity_of(code)` and should normally be
left alone; the block-level E103 precheck is the only caller that overrides it (plan 4.4).
"""
function diag(
    code::AbstractString,
    message::AbstractString;
    hint=nothing,
    path=nothing,
    block=nothing,
    scope=nothing,
    source=nothing,
    node=nothing,
    connection=nothing,
    related=Related[],
    severity=nothing,
)
    return Diagnostic(
        String(code),
        severity === nothing ? severity_of(code) : String(severity),
        String(message),
        _optstr(hint),
        _optstr(path),
        _optstr(block),
        _optstr(scope),
        source,
        _optstr(node),
        _optstr(connection),
        collect(Related, related),
    )
end

"""
    source_kind(ref) -> String

The `SourceRef.kind` for a block reference: `"stdlib"` for `stdlib:...`, `"project"` for
`project:...`, `"inline"` otherwise (plan 3.1).
"""
function source_kind(ref::AbstractString)::String
    startswith(ref, "stdlib:") && return "stdlib"
    startswith(ref, "project:") && return "project"
    return "inline"
end

"""
    to_namedtuple(d::Diagnostic) -> NamedTuple

The plan 3.4 JSON shape as a `NamedTuple`, ready for `JSON3.write`. `nothing` becomes JSON
`null`; the range carries no `file` field, as in the contract.
"""
function to_namedtuple(d::Diagnostic)
    src = if d.source === nothing
        nothing
    else
        r = d.source.range
        (
            kind = d.source.kind,
            ref = d.source.ref,
            range = r === nothing ? nothing :
                    (line = r.line, col = r.col, endLine = r.endLine, endCol = r.endCol),
        )
    end
    return (
        code = d.code,
        severity = d.severity,
        message = d.message,
        hint = d.hint,
        path = d.path,
        block = d.block,
        scope = d.scope,
        source = src,
        node = d.node,
        connection = d.connection,
        related = [(path = rel.path, message = rel.message) for rel in d.related],
    )
end

"""
    to_dict(d::Diagnostic) -> Dict{String,Any}

The same shape as [`to_namedtuple`](@ref), as a `Dict` (for callers that merge diagnostics
into a larger JSON document).
"""
function to_dict(d::Diagnostic)
    return Dict{String,Any}(
        "code" => d.code,
        "severity" => d.severity,
        "message" => d.message,
        "hint" => d.hint,
        "path" => d.path,
        "block" => d.block,
        "scope" => d.scope,
        "source" => d.source === nothing ? nothing : Dict{String,Any}(
            "kind" => d.source.kind,
            "ref" => d.source.ref,
            "range" => d.source.range === nothing ? nothing : Dict{String,Any}(
                "line" => d.source.range.line,
                "col" => d.source.range.col,
                "endLine" => d.source.range.endLine,
                "endCol" => d.source.range.endCol,
            ),
        ),
        "node" => d.node,
        "connection" => d.connection,
        "related" => [
            Dict{String,Any}("path" => rel.path, "message" => rel.message) for
            rel in d.related
        ],
    )
end

"""
    from_dict(d::AbstractDict) -> Diagnostic

Read a diagnostic from the plan 3.4 JSON shape (a `Dict` or a `JSON3.Object`). Missing
optional keys become `nothing`; `severity` is taken from the input when present so that a
round trip is lossless.
"""
function from_dict(d::AbstractDict)
    src = get(d, "source", nothing)
    source = if src === nothing
        nothing
    else
        r = get(src, "range", nothing)
        ref = String(get(src, "ref", ""))
        range = r === nothing ? nothing : SourceRange(
            ref,
            Int(get(r, "line", 1)),
            Int(get(r, "col", 1)),
            Int(get(r, "endLine", get(r, "line", 1))),
            Int(get(r, "endCol", get(r, "col", 1))),
        )
        SourceRef(String(get(src, "kind", source_kind(ref))), ref, range)
    end
    related = Related[
        Related(
            get(rel, "path", nothing) === nothing ? nothing :
            String(get(rel, "path", nothing)),
            String(get(rel, "message", "")),
        ) for rel in get(d, "related", ())
    ]
    code = String(get(d, "code", "E900"))
    return Diagnostic(
        code,
        String(get(d, "severity", severity_of(code))),
        String(get(d, "message", "")),
        _optstr(get(d, "hint", nothing)),
        _optstr(get(d, "path", nothing)),
        _optstr(get(d, "block", nothing)),
        _optstr(get(d, "scope", nothing)),
        source,
        _optstr(get(d, "node", nothing)),
        _optstr(get(d, "connection", nothing)),
        related,
    )
end

"""
    sort_diagnostics(v) -> Vector{Diagnostic}

Order by `(path, line, col, code)` so that two runs of the same check produce the same JSON
(the editor's diffing and the tests rely on it). Diagnostics without a path or source sort
first within their group. The sort is stable.
"""
function sort_diagnostics(v::AbstractVector{<:Diagnostic})
    key(d::Diagnostic) = (
        something(d.path, ""),
        d.source === nothing || d.source.range === nothing ? 0 : d.source.range.line,
        d.source === nothing || d.source.range === nothing ? 0 : d.source.range.col,
        d.code,
    )
    return sort(collect(v); by = key)
end
