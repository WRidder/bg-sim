# Parsing: JuliaSyntax -> our AST (plan 4.1). Never `eval`, never `Meta.parse`-and-eval.
#
# `JuliaSyntax.parseall(SyntaxNode, text; filename, ignore_errors=false)` is called first; a
# `ParseError` becomes one E000 per error-level diagnostic with the parser's range and
# message. Otherwise the `SyntaxNode` tree is walked and converted to the immutable AST in
# `ast.jl`. The parser refuses only syntax it cannot represent (E001); what a construct is
# *allowed* to do is decided by `check_block` against `whitelist.jl`.
#
# The JuliaSyntax API used here was probed on the installed 1.0.2 (see NOTES.md):
# `kind`, `children`, `is_leaf`, `byte_range`, `sourcefile`, `source_location`, `untokenize`,
# and `Base.isoperator` for telling an infix operator leaf from an ordinary identifier.

using JuliaSyntax: SyntaxNode, kind, children, is_leaf, byte_range, sourcefile,
    source_location

# ---------------------------------------------------------------------------------------
# Scope tables
# ---------------------------------------------------------------------------------------

const DECLARATION_SCOPES =
    Symbol[:constants, :parameters, :inputs, :outputs, :ports, :variables]

const SCOPE_MACROS = Dict{Symbol,Symbol}(
    Symbol("@constants") => :constants,
    Symbol("@parameters") => :parameters,
    Symbol("@inputs") => :inputs,
    Symbol("@outputs") => :outputs,
    Symbol("@ports") => :ports,
    Symbol("@variables") => :variables,
    Symbol("@initial") => :initial,
    Symbol("@equations") => :equations,
    Symbol("@discrete") => :discrete,
    Symbol("@events") => :events,
    Symbol("@causality") => :causality,
    Symbol("@components") => :components,
    Symbol("@connections") => :connections,
)

# Scopes that exist in the spec but belong to a later work package. They must be *rejected*
# with a clear E001 that names the scope, never silently ignored.
const UNSUPPORTED_SCOPES = Dict{Symbol,String}()

const ALL_SCOPE_NAMES =
    "@constants @parameters @inputs @outputs @ports @variables @initial @equations " *
    "@discrete @events @causality @components @connections"

const POWER_DOMAINS = Set{Symbol}(
    [:Electrical, :Translation, :Rotation, :Hydraulic, :Generic, :Planar, :Spatial]
)

# Which declaration attributes each scope accepts (plan 4.3 and the spec's attribute table).
const ATTRIBUTE_SCOPES = Dict{Symbol,Vector{Symbol}}(
    :unit => Symbol[:constants, :parameters, :inputs, :outputs, :variables],
    :min => Symbol[:constants, :parameters, :inputs, :outputs, :variables],
    :max => Symbol[:constants, :parameters, :inputs, :outputs, :variables],
    :nominal => Symbol[:variables],
    :tunable => Symbol[:parameters],
    :description => Symbol[:constants, :parameters, :inputs, :outputs, :ports, :variables],
    :state => Symbol[:variables],
    :options => Symbol[:parameters, :constants],
    :structural => Symbol[:constants],
)

const ATTRIBUTE_NAMES =
    "unit, min, max, tunable, description, nominal, state, options, structural"

# ---------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------

_children(node) = is_leaf(node) ? SyntaxNode[] : children(node)

function _range(node, filename::String)
    br = byte_range(node)
    sf = sourcefile(node)
    if last(br) < first(br)
        l, c = source_location(sf, first(br))
        return SourceRange(filename, l, c, l, c)
    end
    l1, c1 = source_location(sf, first(br))
    l2, c2 = source_location(sf, last(br))
    (l2, c2) < (l1, c1) && ((l2, c2) = (l1, c1))
    return SourceRange(filename, l1, c1, l2, c2)
end

function _range(sf, b1::Integer, b2::Integer, filename::String)
    if b2 < b1
        l, c = source_location(sf, b1)
        return SourceRange(filename, l, c, l, c)
    end
    l1, c1 = source_location(sf, b1)
    l2, c2 = source_location(sf, b2)
    (l2, c2) < (l1, c1) && ((l2, c2) = (l1, c1))
    return SourceRange(filename, l1, c1, l2, c2)
end

function _slice(text::String, node)
    br = byte_range(node)
    last(br) < first(br) && return ""
    return String(text[first(br):last(br)])
end

_leaf_symbol(node) = is_leaf(node) && kind(node) == K"Identifier" ? node.val : nothing

"""
    source_range(node::JuliaSyntax.SyntaxNode) -> SourceRange

The range of a raw JuliaSyntax node, so `diag(code, message, pb, node)` also works while a
caller is still walking `SyntaxNode`s. The AST nodes carry their own range (plan 4.1).
"""
source_range(node::SyntaxNode) = _range(node, JuliaSyntax.filename(node))

_macro_name(node) =
    kind(node) == K"macrocall" && !isempty(_children(node)) &&
    kind(_children(node)[1]) == K"MacroName" ? _children(node)[1].val : nothing

"Human label for a syntax kind, for E001 messages."
function _label(node)
    k = kind(node)
    k == K"while" && return "`while` loop"
    k == K"for" && return "`for` loop"
    k == K"if" && return "`if` statement"
    k == K"function" && return "function definition"
    k == K"do" && return "`do` block"
    k == K"let" && return "`let` block"
    k == K"macrocall" && return "macro call"
    k == K"string" && return "string"
    k == K"quote" && return "symbol literal"
    k == K"ref" && return "index expression"
    k == K"." && return "dotted access"
    k == K"=" && return "assignment `=`"
    k == K"op=" && return "compound assignment"
    k == K"?" && return "`? :` expression"
    k == K"dotcall" && return "broadcast call"
    k == K"comparison" && return "chained comparison"
    k == K"curly" && return "type application"
    k == K"::" && return "type annotation"
    k == K"toplevel" && return "statement sequence"
    k == K"block" && return "`begin ... end` block"
    k == K"in" && return "`in` clause"
    return "`" * lowercase(JuliaSyntax.untokenize(k)) * "`"
end

function _is_operator_node(node)
    k = kind(node)
    k == K"Identifier" && return Base.isoperator(node.val)
    return k == K"in" || k == K"isa" || k == K"where"
end

function _operator_symbol(node)
    k = kind(node)
    k == K"Identifier" && return node.val
    k == K"in" && return :in
    k == K"isa" && return :isa
    k == K"where" && return :where
    return nothing
end

# A `begin ... end` grouping is transparent: expand it into its children.
function _flatten_blocks(nodes)
    out = Any[]
    for n in nodes
        if kind(n) == K"block"
            append!(out, _flatten_blocks(_children(n)))
        else
            push!(out, n)
        end
    end
    return out
end

# ---------------------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------------------

mutable struct BlockBuilder
    name::Symbol
    ref::String
    text::String
    filename::String
    scope_list::Vector{Symbol}
    declaration_map::Dict{Symbol,Vector{Decl}}
    equation_items::Vector{Any}
    initial_items::Vector{Any}
    discrete_items::Vector{Any}
    event_items::Vector{Any}
    causality_items::Vector{CausalityDecl}
    component_items::Vector{ComponentDecl}
    connection_items::Vector{ConnectDecl}
    diagnostics::Vector{Diagnostic}
    range::SourceRange
    size_refs::Set{Symbol}
end

function BlockBuilder(name, ref, text, filename, range)
    return BlockBuilder(
        Symbol(name),
        String(ref),
        String(text),
        String(filename),
        Symbol[],
        Dict{Symbol,Vector{Decl}}(s => Decl[] for s in DECLARATION_SCOPES),
        Any[],
        Any[],
        Any[],
        Any[],
        CausalityDecl[],
        ComponentDecl[],
        ConnectDecl[],
        Diagnostic[],
        range,
        Set{Symbol}(),
    )
end

function _error!(b::BlockBuilder, code, message, node = nothing; scope = nothing, hint = nothing)
    node === nothing && (node = b.range)
    node isa SyntaxNode && (node = _range(node, b.filename))
    push!(b.diagnostics, diag(code, message, _as_parsed_stub(b), node; scope = scope, hint = hint))
    return nothing
end

# `diag(code, message, pb, node)` needs a ParsedBlock; during parsing we only have a builder.
# A throw-away block carrying the ref is enough to fill `block` and `source`.
function _as_parsed_stub(b::BlockBuilder)
    return ParsedBlock(
        b.name,
        b.ref,
        b.text,
        b.filename,
        b.scope_list,
        b.declaration_map,
        b.equation_items,
        b.initial_items,
        b.discrete_items,
        b.event_items,
        b.causality_items,
        b.component_items,
        b.connection_items,
        b.diagnostics,
        b.range,
    )
end

function _finish(b::BlockBuilder)
    return ParsedBlock(
        b.name,
        b.ref,
        b.text,
        b.filename,
        b.scope_list,
        b.declaration_map,
        b.equation_items,
        b.initial_items,
        b.discrete_items,
        b.event_items,
        b.causality_items,
        b.component_items,
        b.connection_items,
        b.diagnostics,
        b.range,
    )
end

# ---------------------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------------------

"""
    parse_block(text; filename = "<inline>", ref = "inline:x") -> ParsedBlock

Parse one `@block Name begin ... end` from `text`. `ref` is the block reference used in
diagnostics and `source` (plan 3.1: `stdlib:...`, `project:...` or `inline:...`).

Parse errors produce E000 diagnostics in `block_diagnostics(pb)` (and in the list that
`check_block` returns) and an empty AST. Structural problems — a statement outside a
`@block`, a scope that is not supported yet, a malformed declaration — produce E001 and the
offending item is skipped. Nothing is evaluated.
"""
function parse_block(
    text::AbstractString;
    filename::AbstractString = "<inline>",
    ref::AbstractString = "inline:x",
)
    blocks = _parse_all(String(text), String(filename), String[String(ref)])
    if length(blocks) == 1
        return blocks[1]
    end
    first_block = blocks[1]
    for pb in blocks[2:end]
        push!(
            first_block.diagnostics,
            diag(
                "E001",
                "a block source must contain exactly one `@block`; found another `@block $(block_name(pb))`",
                first_block,
                block_range(pb);
                hint = "put each block in its own file or parse it with `parse_blocks`",
            ),
        )
    end
    return first_block
end

"""
    parse_blocks(text; filename = "<inline>", refs = String[]) -> Vector{ParsedBlock}

Parse every top-level `@block` in `text` (plan 4.1: "one or more `@block Name begin ... end`").
`refs` gives the block reference per block in source order; missing entries fall back to
`inline:<name>`. Statements outside a block produce E001 on the first block (or on an empty
block when there is none).
"""
function parse_blocks(
    text::AbstractString;
    filename::AbstractString = "<inline>",
    refs::AbstractVector{<:AbstractString} = String[],
)
    return _parse_all(String(text), String(filename), String[String(r) for r in refs])
end

function _parse_all(src::String, filename::String, refs::Vector{String})
    if isempty(strip(src))
        ref = isempty(refs) ? "inline:x" : refs[1]
        b = BlockBuilder(Symbol(""), ref, src, filename, SourceRange(filename, 1, 1, 1, 1))
        _error!(
            b,
            "E001",
            "a block source must contain one `@block Name begin ... end`";
            hint = "start with `@block Name begin` and close it with `end`",
        )
        return ParsedBlock[_finish(b)]
    end

    tree = try
        JuliaSyntax.parseall(
            SyntaxNode, src; filename = filename, ignore_errors = false, ignore_warnings = true
        )
    catch err
        err isa JuliaSyntax.ParseError || rethrow()
        ref = isempty(refs) ? "inline:x" : refs[1]
        return ParsedBlock[_syntax_error_block(src, filename, ref, err)]
    end

    blocks = ParsedBlock[]
    file_diags = Diagnostic[]
    default_ref = isempty(refs) ? "inline:x" : refs[1]
    for node in _children(tree)
        if _macro_name(node) === Symbol("@block")
            ref = if length(blocks) < length(refs)
                refs[length(blocks) + 1]
            else
                nm = length(_children(node)) >= 2 ? _leaf_symbol(_children(node)[2]) : nothing
                nm === nothing ? "inline:block$(length(blocks) + 1)" :
                "inline:" * lowercase(String(nm))
            end
            push!(blocks, _parse_block_node(node, src, filename, ref))
        else
            # A statement outside a block. Keep it; it is attached to the first block below.
            r = _range(node, filename)
            push!(
                file_diags,
                diag(
                    "E001",
                    "only `@block Name begin ... end` is allowed at the top level, found $(_label(node))";
                    hint = "wrap the statements in a block",
                    block = default_ref,
                    source = SourceRef(source_kind(default_ref), default_ref, r),
                ),
            )
        end
    end

    if isempty(blocks)
        b = BlockBuilder(Symbol(""), default_ref, src, filename, SourceRange(filename, 1, 1, 1, 1))
        append!(b.diagnostics, file_diags)
        if isempty(file_diags)
            _error!(b, "E001", "a block source must contain one `@block Name begin ... end`")
        end
        return ParsedBlock[_finish(b)]
    end
    isempty(file_diags) || prepend!(blocks[1].diagnostics, file_diags)
    return blocks
end

function _syntax_error_block(src::String, filename::String, ref::String, err)
    diags = Diagnostic[]
    for d in err.diagnostics
        d.level === :error || continue
        r = _range(err.source, d.first_byte, d.last_byte, filename)
        msg = "syntax error: " * lowercasefirst(d.message)
        hint = d.message == "Expected `end`" ? "add `end` to close the block or scope" : nothing
        push!(
            diags,
            diag(
                "E000",
                msg;
                hint = hint,
                block = ref,
                source = SourceRef(source_kind(ref), ref, r),
            ),
        )
    end
    if isempty(diags)
        push!(
            diags,
            diag(
                "E000",
                "syntax error: the source could not be parsed";
                block = ref,
                source = SourceRef(source_kind(ref), ref, SourceRange(filename, 1, 1, 1, 1)),
            ),
        )
    end
    r = diags[1].source === nothing ? SourceRange(filename, 1, 1, 1, 1) :
        something(diags[1].source.range, SourceRange(filename, 1, 1, 1, 1))
    return ParsedBlock(
        Symbol(""),
        ref,
        src,
        filename,
        Symbol[],
        Dict{Symbol,Vector{Decl}}(s => Decl[] for s in DECLARATION_SCOPES),
        Any[],
        Any[],
        Any[],
        Any[],
        CausalityDecl[],
        ComponentDecl[],
        ConnectDecl[],
        diags,
        r,
    )
end

function _parse_block_node(node, src::String, filename::String, ref::String)
    ch = _children(node)
    rng = _range(node, filename)
    if length(ch) < 2
        b = BlockBuilder(Symbol(""), ref, _slice(src, node), filename, rng)
        _error!(
            b,
            "E001",
            "a block needs a name and a body: `@block Name begin ... end`";
            hint = "write `@block Name begin ... end`",
        )
        return _finish(b)
    end
    name_node = ch[2]
    name = _leaf_symbol(name_node)
    if name === nothing
        b = BlockBuilder(Symbol(""), ref, _slice(src, node), filename, rng)
        _error!(b, "E001", "a block name must be an identifier", name_node)
        return _finish(b)
    end
    b = BlockBuilder(name, ref, _slice(src, node), filename, rng)
    if length(ch) < 3
        _error!(b, "E001", "block `$name` has no body"; hint = "add the scopes between `begin` and `end`")
        return _finish(b)
    end
    _parse_block_body!(b, ch[3])
    _finalize_block!(b)
    return _finish(b)
end

function _parse_block_body!(b::BlockBuilder, body)
    for stmt in _flatten_blocks(kind(body) == K"block" ? _children(body) : [body])
        _parse_scope_stmt!(b, stmt)
    end
    return nothing
end

function _parse_scope_stmt!(b::BlockBuilder, stmt)
    mname = _macro_name(stmt)
    if mname === nothing
        _error!(
            b,
            "E001",
            "only scope macros are allowed inside a block, found $(_label(stmt))",
            stmt;
            hint = "allowed scopes: $ALL_SCOPE_NAMES",
        )
        return nothing
    end
    scope = get(SCOPE_MACROS, mname, nothing)
    if scope === nothing
        if haskey(UNSUPPORTED_SCOPES, mname)
            _error!(
                b,
                "E001",
                "the `$mname` scope is not supported yet",
                stmt;
                hint = "it arrives with $(UNSUPPORTED_SCOPES[mname]); this release accepts $ALL_SCOPE_NAMES",
                scope = mname,
            )
        else
            _error!(
                b,
                "E001",
                "`$mname` is not a scope",
                stmt;
                hint = "allowed scopes: $ALL_SCOPE_NAMES",
            )
        end
        return nothing
    end
    push!(b.scope_list, scope)
    args = _children(stmt)[2:end]
    if scope == :discrete
        _parse_discrete_scope!(b, args, stmt)
        return nothing
    elseif scope == :events
        _parse_events_scope!(b, args, stmt)
        return nothing
    elseif scope == :components
        _parse_components_scope!(b, args, stmt)
        return nothing
    elseif scope == :connections
        _parse_connections_scope!(b, args, stmt)
        return nothing
    end
    if isempty(args)
        _error!(
            b,
            "E001",
            "the `$mname` scope is empty",
            stmt;
            hint = "declare something, or remove the scope",
            scope = mname,
        )
        return nothing
    end
    if length(args) > 1 || (length(args) == 1 && kind(args[1]) == K"tuple" &&
       !_is_decl_with_attrs(args[1]))
        _error!(
            b,
            "E001",
            "the `$mname` scope takes one declaration per line, not a comma-separated list",
            stmt;
            hint = "use `$mname begin ... end` and put each declaration on its own line",
            scope = mname,
        )
        return nothing
    end
    arg = args[1]
    items = _flatten_blocks(kind(arg) == K"block" ? _children(arg) : [arg])
    if scope in DECLARATION_SCOPES
        for item in items
            decl = _parse_decl!(b, item, scope)
            decl === nothing || push!(b.declaration_map[scope], decl)
        end
    elseif scope == :equations
        for item in items
            eq = _parse_equation_item!(b, item, scope)
            eq === nothing || push!(b.equation_items, eq)
        end
    elseif scope == :initial
        for item in items
            eq = _parse_equation_item!(b, item, scope)
            eq === nothing || push!(b.initial_items, eq)
        end
    elseif scope == :causality
        for item in items
            c = _parse_causality!(b, item)
            c === nothing || push!(b.causality_items, c)
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------------------

function _parse_decl!(b::BlockBuilder, node, scope::Symbol)
    name_node = nothing
    type_node = nothing
    default_node = nothing
    attrs_node = nothing

    if kind(node) == K"::"
        ch = _children(node)
        name_node = ch[1]
        type_node = ch[2]
    elseif kind(node) == K"tuple" && _is_decl_with_attrs(node)
        ch = _children(node)
        lhs = ch[1]
        attrs_node = ch[2]
        if kind(lhs) == K"::"
            lch = _children(lhs)
            name_node = lch[1]
            type_node = lch[2]
        elseif kind(lhs) == K"Identifier"
            name_node = lhs
        else
            _error!(
                b,
                "E001",
                "the left side of a declaration must be a name, found $(_label(lhs))";
                hint = "write `name::Type, [attributes]`",
            )
            return nothing
        end
    elseif kind(node) == K"="
        ch = _children(node)
        lhs, rhs = ch[1], ch[2]
        if kind(lhs) == K"::"
            lch = _children(lhs)
            name_node = lch[1]
            type_node = lch[2]
        elseif kind(lhs) == K"Identifier"
            name_node = lhs
        else
            _error!(
                b,
                "E001",
                "the left side of a declaration must be a name, found $(_label(lhs))";
                hint = "write `name::Type = default, [attributes]`",
            )
            return nothing
        end
        if kind(rhs) == K"tuple" && length(_children(rhs)) == 2 &&
           kind(_children(rhs)[2]) == K"vect"
            default_node = _children(rhs)[1]
            attrs_node = _children(rhs)[2]
        else
            default_node = rhs
        end
    elseif kind(node) == K"Identifier"
        name_node = node
    else
        _error!(
            b,
            "E001",
            "$(_label(node)) is not a declaration";
            hint = "write `name::Type = default, [attributes]`",
        )
        return nothing
    end

    name = _leaf_symbol(name_node)
    if name === nothing
        _error!(b, "E001", "a declaration name must be an identifier", name_node)
        return nothing
    end
    rng = _range(node, b.filename)

    t = REAL
    if type_node !== nothing
        t = _parse_type!(b, type_node)
        t === nothing && return nothing
    end

    default = nothing
    default_text = nothing
    if default_node !== nothing
        default = _to_expr!(b, default_node, scope)
        default === nothing && return nothing
        default_text = _slice(b.text, default_node)
    end

    attrs = Dict{Symbol,Any}()
    attrs_node === nothing || _parse_attrs!(b, attrs_node, attrs, scope)

    return Decl(name, t, default, attrs, scope, rng, default_text)
end

function _parse_type!(b::BlockBuilder, node)
    k = kind(node)
    if k == K"Identifier"
        v = node.val
        v in (:Real, :Int, :Bool) && return TypeSpec(v)
        _error!(
            b,
            "E001",
            "`$v` is not a value type";
            hint = "use Real, Int, Bool, Vec{N}, Mat{N,M} or Power{Domain}",
        )
        return nothing
    elseif k == K"curly"
        ch = _children(node)
        head = _leaf_symbol(ch[1])
        if head === :Vec
            if length(ch) != 2
                _error!(b, "E001", "`Vec` takes one size, as in `Vec{3}`", node)
                return nothing
            end
            arg = _size_arg!(b, ch[2])
            arg === nothing && return nothing
            return TypeSpec(:Vec, (arg,))
        elseif head === :Mat
            if length(ch) != 3
                _error!(b, "E001", "`Mat` takes two sizes, as in `Mat{3,3}`", node)
                return nothing
            end
            a = _size_arg!(b, ch[2])
            c = _size_arg!(b, ch[3])
            (a === nothing || c === nothing) && return nothing
            return TypeSpec(:Mat, (a, c))
        elseif head === :Power
            if length(ch) != 2
                _error!(b, "E001", "`Power` takes one domain, as in `Power{Rotation}`", node)
                return nothing
            end
            dom = _leaf_symbol(ch[2])
            if dom === nothing
                _error!(b, "E001", "a power domain must be an identifier", ch[2])
                return nothing
            end
            if !(dom in POWER_DOMAINS)
                _error!(
                    b,
                    "E001",
                    "`$dom` is not a power domain";
                    hint = "use Electrical, Translation, Rotation, Hydraulic or Generic (Planar and Spatial arrive with M4)",
                )
                return nothing
            end
            return TypeSpec(:Power, (dom,))
        end
        _error!(
            b,
            "E001",
            "`$(something(head, Symbol("")))` is not a value type";
            hint = "use Real, Int, Bool, Vec{N}, Mat{N,M} or Power{Domain}",
        )
        return nothing
    end
    _error!(
        b,
        "E001",
        "$(_label(node)) is not a value type";
        hint = "use Real, Int, Bool, Vec{N}, Mat{N,M} or Power{Domain}",
    )
    return nothing
end

function _size_arg!(b::BlockBuilder, node)
    k = kind(node)
    if k == K"Integer"
        n = Int(node.val)
        if n < 1
            _error!(b, "E005", "array size must be at least 1, got $n", node)
            return nothing
        end
        return n
    elseif k == K"Identifier"
        push!(b.size_refs, node.val)
        return node.val
    elseif k == K"call" && !isempty(_children(node)) && _leaf_symbol(_children(node)[1]) === :ifelse
        # The spec allows `ifelse` in sizes; fold it once the constants are known
        # (`resolve_type` does that with `try_eval_const`).
        e = _to_expr!(b, node, :default)
        e === nothing && return nothing
        _collect_expr_refs!(b.size_refs, e)
        return e
    end
    _error!(
        b,
        "E005",
        "array size must be an integer literal, a `@constants` value or an `ifelse` of them, found $(_label(node))";
        hint = "declare the size in `@constants`, e.g. `@constants N::Int = 3`",
    )
    return nothing
end

function _parse_attrs!(b::BlockBuilder, node, attrs::Dict{Symbol,Any}, scope::Symbol)
    if kind(node) != K"vect"
        _error!(b, "E001", "attributes must be written as `[name = value, ...]`", node)
        return nothing
    end
    for item in _children(node)
        if kind(item) != K"="
            _error!(b, "E001", "an attribute must be written as `name = value`", item)
            continue
        end
        ich = _children(item)
        key_node, value_node = ich[1], ich[2]
        key = _leaf_symbol(key_node)
        if key === nothing
            _error!(b, "E001", "an attribute name must be an identifier", key_node)
            continue
        end
        allowed = get(ATTRIBUTE_SCOPES, key, nothing)
        if allowed === nothing
            _error!(
                b,
                "E001",
                "`$key` is not a declaration attribute",
                key_node;
                hint = "allowed attributes: $ATTRIBUTE_NAMES",
            )
            continue
        end
        if !(scope in allowed)
            _error!(
                b,
                "E001",
                "`$key` is not allowed on $(scope_string(scope)) declarations",
                key_node;
                hint = "`$key` applies to " *
                       join([scope_string(s) for s in allowed], ", "),
            )
            continue
        end
        value = _parse_attr_value!(b, key, value_node, scope)
        value === nothing && continue
        haskey(attrs, key) &&
            _error!(b, "E001", "attribute `$key` is given more than once", key_node)
        attrs[key] = value
    end
    return nothing
end

function _parse_attr_value!(b::BlockBuilder, key::Symbol, node, scope::Symbol)
    if key === :unit || key === :description
        s = _string_literal(node)
        s === nothing &&
            _error!(b, "E001", "`$key` must be a plain string literal, as in `$key = \"...\"`", node)
        return s
    elseif key === :tunable || key === :structural
        kind(node) == K"Bool" && return node.val
        _error!(b, "E001", "`$key` must be `true` or `false`", node)
        return nothing
    elseif key === :state
        if kind(node) == K"quote" && length(_children(node)) == 1
            v = _leaf_symbol(_children(node)[1])
            (v === :prefer || v === :avoid) && return v
        end
        _error!(
            b,
            "E001",
            "`state` must be `:prefer` or `:avoid`";
            hint = "write `state = :prefer`",
        )
        return nothing
    elseif key === :options
        if kind(node) == K"vect"
            out = String[]
            for el in _children(node)
                s = _string_literal(el)
                if s === nothing
                    _error!(b, "E001", "`options` must be a list of string literals", el)
                    return nothing
                end
                push!(out, s)
            end
            return out
        end
        _error!(
            b,
            "E001",
            "`options` must be a list of string literals, as in `[\"hold\", \"linear\"]`",
            node,
        )
        return nothing
    end
    # min, max, nominal: constant expressions, folded once all declarations are known.
    return _to_expr!(b, node, scope)
end

function _string_literal(node)
    kind(node) == K"string" || return nothing
    ch = _children(node)
    length(ch) == 1 && kind(ch[1]) == K"String" || return nothing
    return String(ch[1].val)
end

# `name::Type, [attrs]` (a declaration with attributes but no default) parses as a
# two-element tuple whose second element is the attribute vector. A comma-separated
# declaration list also parses as a tuple, but without a `vect` second element.
_is_decl_with_attrs(node) =
    kind(node) == K"tuple" && length(_children(node)) == 2 &&
    kind(_children(node)[2]) == K"vect"

# ---------------------------------------------------------------------------------------
# Equations
# ---------------------------------------------------------------------------------------

function _parse_equation_item!(b::BlockBuilder, node, scope::Symbol)
    k = kind(node)
    rng = _range(node, b.filename)
    if k == K"call"
        ch = _children(node)
        if length(ch) == 3 && _is_operator_node(ch[2]) && _operator_symbol(ch[2]) === :~
            lhs = _to_expr!(b, ch[1], scope)
            rhs = _to_expr!(b, ch[3], scope)
            (lhs === nothing || rhs === nothing) && return nothing
            return Equation(lhs, rhs, rng, scope)
        elseif length(ch) == 3 && _is_operator_node(ch[2]) &&
               is_comparison_op(_operator_symbol(ch[2]))
            _error!(
                b,
                "E001",
                "a comparison is not an equation",
                node;
                hint = "equations use `~`; comparisons are only allowed inside `ifelse`",
            )
            return nothing
        end
        _error!(
            b,
            "E001",
            "only equations (`lhs ~ rhs`) are allowed in $(scope_string(scope)), found `$(_slice(b.text, node))`",
            node;
            hint = "write `lhs ~ rhs`",
        )
        return nothing
    elseif k == K"="
        _error!(
            b,
            "E001",
            "`=` is not allowed in $(scope_string(scope))",
            node;
            hint = "use `~` for equations",
        )
        return nothing
    elseif k == K"op="
        _error!(
            b,
            "E001",
            "$(_label(node)) is not allowed in $(scope_string(scope))",
            node;
            hint = "assignments are only allowed in `@discrete` and `@events`",
        )
        return nothing
    elseif k == K"function"
        sig = _children(node)[1]
        head = kind(sig) == K"call" && !isempty(_children(sig)) ?
            _leaf_symbol(_children(sig)[1]) : nothing
        if head === :ddt || head === :int
            _error!(
                b,
                "E001",
                "`=` is not allowed in $(scope_string(scope))",
                node;
                hint = "use `~` for equations",
            )
        else
            _error!(
                b,
                "E001",
                "function definitions are not allowed in $(scope_string(scope))",
                node;
                hint = "write equations with `~`; there is no user-defined code",
            )
        end
        return nothing
    elseif k == K"if"
        return _parse_if!(b, node, scope)
    elseif k == K"for"
        return _parse_for!(b, node, scope)
    elseif k == K"while"
        _error!(
            b,
            "E001",
            "`while` loops are not allowed in $(scope_string(scope))",
            node;
            hint = "use a bounded `for i in 1:N` loop; N must be a constant",
        )
        return nothing
    elseif k == K"continue" || k == K"break"
        _error!(
            b,
            "E001",
            "`$(kind(node))` is not allowed in $(scope_string(scope))",
            node;
            hint = "loops are unrolled at compile time, so there is nothing to break out of",
        )
        return nothing
    elseif k == K"block"
        _error!(
            b,
            "E001",
            "a nested `begin ... end` is not allowed in $(scope_string(scope))",
            node;
            hint = "write the equations directly",
        )
        return nothing
    elseif k == K"macrocall"
        _error!(
            b,
            "E001",
            "macros other than the scope macros are not allowed in $(scope_string(scope))",
        )
        return nothing
    elseif k == K"quote"
        _error!(b, "E001", "a symbol literal is not an equation", node)
        return nothing
    end
    _error!(
        b,
        "E001",
        "$(_label(node)) is not allowed in $(scope_string(scope))";
        hint = "write `lhs ~ rhs`",
    )
    return nothing
end

function _eq_body!(b::BlockBuilder, node, scope::Symbol)
    items = _flatten_blocks(kind(node) == K"block" ? _children(node) : [node])
    out = Any[]
    for item in items
        eq = _parse_equation_item!(b, item, scope)
        eq === nothing || push!(out, eq)
    end
    return out
end

function _parse_if!(b::BlockBuilder, node, scope::Symbol)
    ch = _children(node)
    if length(ch) < 2
        _error!(
            b,
            "E001",
            "`if` needs a condition and a body",
            node;
            hint = "write `if cond ... else ... end`",
        )
        return nothing
    end
    branches = EqBranch[]
    push!(
        branches,
        EqBranch(
            _to_expr!(b, ch[1], scope),
            _eq_body!(b, ch[2], scope),
            _range(node, b.filename),
        ),
    )
    _if_rest!(b, branches, ch[3:end], scope)
    return IfEquation(branches, _range(node, b.filename))
end

function _if_rest!(b::BlockBuilder, branches::Vector{EqBranch}, rest, scope::Symbol)
    for node in rest
        k = kind(node)
        if k == K"elseif"
            ch = _children(node)
            push!(
                branches,
                EqBranch(
                    _to_expr!(b, ch[1], scope),
                    _eq_body!(b, ch[2], scope),
                    _range(node, b.filename),
                ),
            )
            _if_rest!(b, branches, ch[3:end], scope)
        elseif k == K"block"
            push!(
                branches,
                EqBranch(nothing, _eq_body!(b, node, scope), _range(node, b.filename)),
            )
        elseif k == K"else"
            ch = _children(node)
            body = isempty(ch) ? Any[] : _eq_body!(b, ch[1], scope)
            push!(branches, EqBranch(nothing, body, _range(node, b.filename)))
        end
    end
    return nothing
end

function _parse_for!(b::BlockBuilder, node, scope::Symbol)
    ch = _children(node)
    if length(ch) < 2
        _error!(
            b,
            "E001",
            "`for` needs a range and a body",
            node;
            hint = "write `for i in 1:N ... end`",
        )
        return nothing
    end
    iter = ch[1]
    if kind(iter) != K"iteration" || length(_children(iter)) != 1
        _error!(
            b,
            "E001",
            "`for` is only allowed with one range, as in `for i in 1:N`";
            hint = "use one `for i in 1:N` per loop",
        )
        return nothing
    end
    clause = _children(iter)[1]
    cch = _children(clause)
    if length(cch) < 2
        _error!(
            b,
            "E001",
            "`for` needs a range `1:N`";
            hint = "`N` must be a `@constants` value",
        )
        return nothing
    end
    var = kind(clause) == K"in" && !isempty(cch) ? _leaf_symbol(cch[1]) : nothing
    if var === nothing
        _error!(b, "E001", "`for` needs a loop variable, as in `for i in 1:N`", clause)
        return nothing
    end
    parts = _range_parts(cch[2])
    if parts === nothing
        _error!(
            b,
            "E001",
            "`for` needs a range `1:N`, found `$(_slice(b.text, cch[2]))`";
            hint = "`N` must be a `@constants` value",
        )
        return nothing
    end
    lo = _to_expr!(b, parts[1], scope)
    hi = _to_expr!(b, parts[2], scope)
    step = parts[3] === nothing ? nothing : _to_expr!(b, parts[3], scope)
    (lo === nothing || hi === nothing || (parts[3] !== nothing && step === nothing)) &&
        return nothing
    body = _eq_body!(b, ch[2], scope)
    return ForEquation(var, lo, hi, step, body, _range(node, b.filename))
end

function _range_parts(node)
    kind(node) == K"call" || return nothing
    ch = _children(node)
    (length(ch) == 3 || length(ch) == 4) || return nothing
    _is_operator_node(ch[2]) || return nothing
    _operator_symbol(ch[2]) === Symbol(":") || return nothing
    return length(ch) == 3 ? (ch[1], ch[3], nothing) : (ch[1], ch[4], ch[3])
end

# ---------------------------------------------------------------------------------------
# @initial
# ---------------------------------------------------------------------------------------
#
# `@initial` reuses the equation walker with `scope = :initial`; `check_block` gives it the
# initial semantics (no `ddt`) and keeps it out of the balance count. Nothing extra is
# needed in the parser beyond the dispatch in `_parse_scope_stmt!`.

# ---------------------------------------------------------------------------------------
# @discrete and @events (J2.1, decisions D18 and D19)
# ---------------------------------------------------------------------------------------

"""
Parse one `@discrete Ts = <period> begin ... end` scope. The header accepts the spec's
`Ts = 1e-3` form, the bare form `@discrete 1e-3`, and an `offset` attribute in either
spelling (`Ts = 1e-3, [offset = 1e-4]` or `Ts = 1e-3 [offset = 1e-4]`). The body is a
statement list; the period and offset are folded in `_finalize_block!`.
"""
function _parse_discrete_scope!(b::BlockBuilder, args, stmt)
    rng = _range(stmt, b.filename)
    if length(args) == 1 && kind(args[1]) == K"block"
        _error!(
            b,
            "E001",
            "`@discrete` needs a clock period, as in `@discrete Ts = 1e-3 begin ... end`",
            stmt;
            scope = :discrete,
            hint = "write `Ts = <period>` before the body; `Ts` is readable inside the body",
        )
        return nothing
    end
    header, attrs_node, body_node = _split_discrete_args(b, args, stmt)
    header === nothing && return nothing
    parsed = _parse_discrete_header!(b, header)
    parsed === nothing && return nothing
    period, embedded_attrs = parsed
    if attrs_node !== nothing && embedded_attrs !== nothing
        _error!(
            b,
            "E001",
            "write the `@discrete` attributes once",
            stmt;
            scope = :discrete,
            hint = "use either `Ts = 1e-3, [offset = ...]` or `Ts = 1e-3 [offset = ...]`",
        )
        return nothing
    end
    offset = _parse_discrete_attrs!(
        b, attrs_node === nothing ? embedded_attrs : attrs_node
    )
    body = _parse_stmt_list!(b, body_node, :discrete)
    if isempty(body)
        _error!(
            b,
            "E001",
            "the `@discrete` scope is empty",
            body_node;
            scope = :discrete,
            hint = "assign something inside the body, or remove the scope",
        )
        return nothing
    end
    push!(b.discrete_items, DiscreteScope(period, offset, body, rng, nothing, nothing))
    return nothing
end

"""Split the macrocall arguments of `@discrete`. The period is one argument and the body a
`begin ... end`; the plan also writes `Ts = 1e-3 [offset = 1e-4] begin ... end`, which
JuliaSyntax parses as three arguments (the attribute vector is separate)."""
function _split_discrete_args(b::BlockBuilder, args, stmt)
    if length(args) == 3 && kind(args[2]) == K"vect" && kind(args[3]) == K"block"
        return (args[1], args[2], args[3])
    elseif length(args) == 2 && kind(args[2]) == K"block"
        return (args[1], nothing, args[2])
    end
    _error!(
        b,
        "E001",
        "`@discrete` takes one clock period and one `begin ... end` body",
        stmt;
        scope = :discrete,
        hint = "write `@discrete Ts = 1e-3 begin ... end`",
    )
    return (nothing, nothing, nothing)
end

function _parse_discrete_header!(b::BlockBuilder, header)
    if kind(header) == K"="
        ch = _children(header)
        if length(ch) != 2
            _error!(b, "E001", "the `@discrete` period is `Ts = <period>`", header; scope = :discrete)
            return nothing
        end
        name = _leaf_symbol(ch[1])
        if name !== :Ts
            _error!(
                b,
                "E001",
                "the `@discrete` period is written `Ts = <period>`",
                ch[1];
                scope = :discrete,
                hint = "`Ts` names the clock period inside the body",
            )
            return nothing
        end
        value_node = ch[2]
        attrs_node = nothing
        if kind(value_node) == K"tuple" && length(_children(value_node)) == 2 &&
           kind(_children(value_node)[2]) == K"vect"
            attrs_node = _children(value_node)[2]
            value_node = _children(value_node)[1]
        end
        period = _to_expr!(b, value_node, :discrete)
        period === nothing && return nothing
        return (period, attrs_node)
    end
    period = _to_expr!(b, header, :discrete)
    period === nothing && return nothing
    return (period, nothing)
end

function _parse_discrete_attrs!(b::BlockBuilder, attrs_node)
    attrs_node === nothing && return nothing
    offset = nothing
    for item in _children(attrs_node)
        if kind(item) != K"="
            _error!(b, "E001", "a `@discrete` attribute is `name = value`", item; scope = :discrete)
            continue
        end
        ich = _children(item)
        key = length(ich) == 2 ? _leaf_symbol(ich[1]) : nothing
        if key !== :offset
            _error!(
                b,
                "E001",
                "`$(something(key, Symbol("")))` is not an `@discrete` attribute",
                isempty(ich) ? item : ich[1];
                scope = :discrete,
                hint = "the only `@discrete` attribute is `offset`",
            )
            continue
        end
        offset === nothing ||
            _error!(b, "E001", "`offset` is given more than once", ich[1]; scope = :discrete)
        offset = _to_expr!(b, ich[2], :discrete)
    end
    return offset
end

"""
Parse one `@events` scope. Every entry is `cond => begin ... end`; `cond` may be a real
expression or a `<` / `>` comparison (D19). Entries may be separated by newlines or `;`.
"""
function _parse_events_scope!(b::BlockBuilder, args, stmt)
    if length(args) != 1
        _error!(
            b,
            "E001",
            "`@events` takes one `begin ... end` body of `cond => begin ... end` entries";
            scope = :events,
            hint = "write `@events begin cond => begin ... end end`",
        )
        return nothing
    end
    arg = args[1]
    items = _flatten_blocks(kind(arg) == K"block" ? _children(arg) : [arg])
    if isempty(items)
        _error!(
            b,
            "E001",
            "the `@events` scope is empty",
            arg;
            scope = :events,
            hint = "add an entry `cond => begin ... end`, or remove the scope",
        )
        return nothing
    end
    for item in items
        _parse_event!(b, item)
    end
    return nothing
end

function _parse_event!(b::BlockBuilder, node)
    rng = _range(node, b.filename)
    ch = _children(node)
    if !(kind(node) == K"call" && length(ch) == 3 && _is_operator_node(ch[2]) &&
         _operator_symbol(ch[2]) === Symbol("=>"))
        _error!(
            b,
            "E001",
            "an `@events` entry is `cond => begin ... end`",
            node;
            scope = :events,
            hint = "write the trigger on the left of `=>` and the statements in a `begin ... end` body",
        )
        return nothing
    end
    cond = _to_expr!(b, ch[1], :events)
    cond === nothing && return nothing
    body = _parse_stmt_list!(b, ch[3], :events)
    push!(b.event_items, EventDecl(cond, body, rng))
    return nothing
end

# ---------------------------------------------------------------------------------------
# @components and @connections (J2.6, decision D5)
# ---------------------------------------------------------------------------------------

"""
Parse one `@components begin name = BlockName(kw = expr, ...) ... end` scope. Every entry
declares an internal instance of a block (resolved by name at instantiation); the keyword
arguments are parameter overrides in the defaults expression scope. Positional arguments
are refused: a component's parameters are named, so a positional argument cannot be bound.
"""
function _parse_components_scope!(b::BlockBuilder, args, stmt)
    if length(args) != 1
        _error!(
            b,
            "E001",
            "`@components` takes one `begin ... end` body of `name = BlockName(...)` entries";
            scope = :components,
            hint = "write `@components begin gear = LossyGear(n = 10.0) end`",
        )
        return nothing
    end
    arg = args[1]
    if kind(arg) == K"block" && isempty(_flatten_blocks(_children(arg)))
        _error!(
            b,
            "E001",
            "the `@components` scope is empty",
            arg;
            scope = :components,
            hint = "declare an instance, or remove the scope",
        )
        return nothing
    end
    items = _flatten_blocks(kind(arg) == K"block" ? _children(arg) : [arg])
    for item in items
        _parse_component!(b, item)
    end
    return nothing
end

function _parse_component!(b::BlockBuilder, node)
    rng = _range(node, b.filename)
    if kind(node) != K"="
        _error!(
            b,
            "E001",
            "an `@components` entry is `name = BlockName(parameter = value, ...)`",
            node;
            scope = :components,
            hint = "write `gear = LossyGear(n = 10.0)`",
        )
        return nothing
    end
    ch = _children(node)
    name = length(ch) == 2 ? _leaf_symbol(ch[1]) : nothing
    if name === nothing
        _error!(b, "E001", "a component name must be an identifier", isempty(ch) ? node : ch[1];
            scope = :components)
        return nothing
    end
    rhs = ch[2]
    if kind(rhs) != K"call" || isempty(_children(rhs))
        _error!(
            b,
            "E001",
            "component `$name` must be an instance of a block, as in `$name = LossyGear(n = 10.0)`",
            rhs;
            scope = :components,
            hint = "a component is `name = BlockName(...)`; a junction or a subsystem uses the model JSON",
        )
        return nothing
    end
    cch = _children(rhs)
    block = _leaf_symbol(cch[1])
    if block === nothing
        _error!(
            b,
            "E001",
            "the block of component `$name` must be a plain block name",
            cch[1];
            scope = :components,
            hint = "write the block name without a module or a path, e.g. `LossyGear`",
        )
        return nothing
    end
    kwargs = Pair{Symbol,Expr}[]
    ok = true
    for a in cch[2:end]
        if kind(a) != K"="
            _error!(
                b,
                "E001",
                "component `$name` takes named parameter overrides only",
                a;
                scope = :components,
                hint = "write `$(block)(parameter = value, ...)`; positional arguments have no meaning",
            )
            ok = false
            continue
        end
        ach = _children(a)
        key = length(ach) == 2 ? _leaf_symbol(ach[1]) : nothing
        if key === nothing
            _error!(b, "E001", "a component parameter override is `name = value`", a;
                scope = :components)
            ok = false
            continue
        end
        value = _to_expr!(b, ach[2], :components)
        value === nothing && (ok = false; continue)
        any(k -> first(k) === key, kwargs) && (
            _error!(
                b,
                "E003",
                "parameter `$key` of component `$name` is overridden twice",
                a;
                scope = :components,
                hint = "give each parameter of a component one value",
            );
            ok = false
        )
        push!(kwargs, key => value)
    end
    ok || return nothing
    push!(b.component_items, ComponentDecl(name, block, kwargs, rng))
    return nothing
end

"""
Parse one `@connections begin connect(a, b) ... end` scope. Each side of a `connect` is a
port of this block (`a`) or a port of one of its components (`gear.a`). Both power and
signal ports are written the same way: the port declarations decide what the connection
means (J2.6, plan D7).
"""
function _parse_connections_scope!(b::BlockBuilder, args, stmt)
    if length(args) != 1
        _error!(
            b,
            "E001",
            "`@connections` takes one `begin ... end` body of `connect(a, b)` entries";
            scope = :connections,
            hint = "write `@connections begin connect(a, gear.a) end`",
        )
        return nothing
    end
    arg = args[1]
    if kind(arg) == K"block" && isempty(_flatten_blocks(_children(arg)))
        _error!(
            b,
            "E001",
            "the `@connections` scope is empty",
            arg;
            scope = :connections,
            hint = "connect two ports, or remove the scope",
        )
        return nothing
    end
    items = _flatten_blocks(kind(arg) == K"block" ? _children(arg) : [arg])
    for item in items
        _parse_connect!(b, item)
    end
    return nothing
end

function _parse_connect!(b::BlockBuilder, node)
    rng = _range(node, b.filename)
    ch = _children(node)
    if !(kind(node) == K"call" && !isempty(ch) && _leaf_symbol(ch[1]) === :connect &&
         length(ch) == 3)
        _error!(
            b,
            "E001",
            "an `@connections` entry is `connect(portA, portB)`",
            node;
            scope = :connections,
            hint = "write `connect(gear.b, play.a)`, with a port of this block or `instance.port` on each side",
        )
        return nothing
    end
    from = _parse_portref!(b, ch[2])
    to = _parse_portref!(b, ch[3])
    (from === nothing || to === nothing) && return nothing
    push!(b.connection_items, ConnectDecl(from, to, rng))
    return nothing
end

function _parse_portref!(b::BlockBuilder, node)
    rng = _range(node, b.filename)
    k = kind(node)
    if k == K"Identifier"
        name = _leaf_symbol(node)
        if name === nothing
            _error!(b, "E001", "a port name must be an identifier", node; scope = :connections)
            return nothing
        end
        return PortRef(nothing, name, rng)
    elseif k == K"."
        ch = _children(node)
        instance = length(ch) == 2 ? _leaf_symbol(ch[1]) : nothing
        port = length(ch) == 2 ? _leaf_symbol(ch[2]) : nothing
        if instance === nothing || port === nothing
            _error!(
                b,
                "E001",
                "a component port is written `instance.port`",
                node;
                scope = :connections,
            )
            return nothing
        end
        return PortRef(instance, port, rng)
    end
    _error!(
        b,
        "E001",
        "a `connect` side is a port (`a`) or a component port (`gear.a`)",
        node;
        scope = :connections,
        hint = "nested component paths are not supported; connect `instance.port`",
    )
    return nothing
end

# --- statements ------------------------------------------------------------------------

function _parse_stmt_list!(b::BlockBuilder, node, scope::Symbol)
    items = _flatten_blocks(kind(node) == K"block" ? _children(node) : [node])
    out = Any[]
    for item in items
        s = _parse_stmt!(b, item, scope)
        s === nothing || push!(out, s)
    end
    return out
end

function _parse_stmt!(b::BlockBuilder, node, scope::Symbol)
    k = kind(node)
    rng = _range(node, b.filename)
    if k == K"="
        ch = _children(node)
        length(ch) == 2 || (_error!(b, "E001", "an assignment is `target = value`", node; scope = scope); return nothing)
        target = _to_expr!(b, ch[1], scope)
        value = _to_expr!(b, ch[2], scope)
        (target === nothing || value === nothing) && return nothing
        return Assign(target, value, :assign, rng, scope)
    elseif k == K"op="
        ch = _children(node)
        length(ch) == 3 ||
            (_error!(b, "E001", "a compound assignment is `target += value`", node; scope = scope); return nothing)
        op = _operator_symbol(ch[2])
        if !(op in (:+, :-, :*, :/))
            _error!(
                b,
                "E001",
                "`$(something(op, Symbol(""))) =` is not an allowed compound assignment",
                node;
                scope = scope,
                hint = "use `=`, `+=`, `-=`, `*=` or `/=`",
            )
            return nothing
        end
        target = _to_expr!(b, ch[1], scope)
        value = _to_expr!(b, ch[3], scope)
        (target === nothing || value === nothing) && return nothing
        return Assign(target, value, op, rng, scope)
    elseif k == K"if"
        return _parse_if_stmt!(b, node, scope)
    elseif k == K"for"
        return _parse_for_stmt!(b, node, scope)
    elseif k == K"while"
        _error!(
            b,
            "E001",
            "`while` loops are not allowed in $(scope_string(scope))",
            node;
            scope = scope,
            hint = "use a bounded `for i in 1:N` loop; N must be a constant",
        )
        return nothing
    elseif k == K"break" || k == K"continue"
        _error!(
            b,
            "E001",
            "`$(kind(node))` is not allowed in $(scope_string(scope))",
            node;
            scope = scope,
            hint = "loops are unrolled at compile time, so there is nothing to break out of",
        )
        return nothing
    elseif k == K"call"
        ch = _children(node)
        if length(ch) == 3 && _is_operator_node(ch[2])
            op = _operator_symbol(ch[2])
            if op === :~
                _error!(
                    b,
                    "E001",
                    "`~` is not allowed in $(scope_string(scope))",
                    node;
                    scope = scope,
                    hint = "use `=` to assign in discrete code",
                )
                return nothing
            elseif op === Symbol("=>")
                _error!(
                    b,
                    "E001",
                    "`=>` is only allowed in `@causality` and as an `@events` entry",
                    node;
                    scope = scope,
                )
                return nothing
            end
        end
        expr = _to_expr!(b, node, scope)
        expr === nothing && return nothing
        if expr isa Call
            return CallStatement(expr, rng, scope)
        end
        _error!(
            b,
            "E001",
            "a bare expression is not a statement in $(scope_string(scope))",
            node;
            scope = scope,
            hint = "only `reinit(x, value)` is a call statement, and only in `@events`",
        )
        return nothing
    elseif k == K"function" || k == K"do"
        _error!(
            b,
            "E001",
            "function definitions and `do` blocks are not allowed in $(scope_string(scope))",
            node;
            scope = scope,
        )
        return nothing
    elseif k == K"macrocall"
        _error!(b, "E001", "macros are not allowed in $(scope_string(scope))", node; scope = scope)
        return nothing
    elseif k == K"::"
        _error!(
            b,
            "E001",
            "a typed local declaration is not allowed in $(scope_string(scope))",
            node;
            scope = scope,
            hint = "assign a value to an undeclared name to create a temporary (D18)",
        )
        return nothing
    elseif k == K"block"
        _error!(
            b,
            "E001",
            "a nested `begin ... end` is not allowed in $(scope_string(scope))",
            node;
            scope = scope,
        )
        return nothing
    end
    _error!(
        b,
        "E001",
        "$(_label(node)) is not a statement in $(scope_string(scope))";
        scope = scope,
        hint = "allowed statements: assignment, `if`, `for`, and `reinit` in `@events`",
    )
    return nothing
end

function _parse_if_stmt!(b::BlockBuilder, node, scope::Symbol)
    ch = _children(node)
    rng = _range(node, b.filename)
    if length(ch) < 2
        _error!(
            b,
            "E001",
            "`if` needs a condition and a body",
            node;
            scope = scope,
            hint = "write `if cond ... else ... end`",
        )
        return nothing
    end
    branches = StmtBranch[]
    cond = _to_expr!(b, ch[1], scope)
    cond === nothing && (cond = Lit(false, rng))
    push!(branches, StmtBranch(cond, _parse_stmt_list!(b, ch[2], scope), rng))
    _if_stmt_rest!(b, branches, ch[3:end], scope)
    return IfStatement(branches, rng, scope)
end

function _if_stmt_rest!(b::BlockBuilder, branches::Vector{StmtBranch}, rest, scope::Symbol)
    for node in rest
        k = kind(node)
        if k == K"elseif"
            ch = _children(node)
            rng = _range(node, b.filename)
            cond = _to_expr!(b, ch[1], scope)
            cond === nothing && (cond = Lit(false, rng))
            push!(branches, StmtBranch(cond, _parse_stmt_list!(b, ch[2], scope), rng))
            _if_stmt_rest!(b, branches, ch[3:end], scope)
        elseif k == K"block"
            push!(
                branches,
                StmtBranch(nothing, _parse_stmt_list!(b, node, scope), _range(node, b.filename)),
            )
        elseif k == K"else"
            ch = _children(node)
            rng = _range(node, b.filename)
            body = isempty(ch) ? Any[] : _parse_stmt_list!(b, ch[1], scope)
            push!(branches, StmtBranch(nothing, body, rng))
        end
    end
    return nothing
end

function _parse_for_stmt!(b::BlockBuilder, node, scope::Symbol)
    ch = _children(node)
    rng = _range(node, b.filename)
    if length(ch) < 2
        _error!(
            b,
            "E001",
            "`for` needs a range and a body",
            node;
            scope = scope,
            hint = "write `for i in 1:N ... end`",
        )
        return nothing
    end
    iter = ch[1]
    if kind(iter) != K"iteration" || length(_children(iter)) != 1
        _error!(
            b,
            "E001",
            "`for` is only allowed with one range, as in `for i in 1:N`";
            scope = scope,
            hint = "use one `for i in 1:N` per loop",
        )
        return nothing
    end
    clause = _children(iter)[1]
    cch = _children(clause)
    if length(cch) < 2
        _error!(
            b,
            "E001",
            "`for` needs a range `1:N`";
            scope = scope,
            hint = "`N` must be a `@constants` value",
        )
        return nothing
    end
    var = kind(clause) == K"in" && !isempty(cch) ? _leaf_symbol(cch[1]) : nothing
    if var === nothing
        _error!(b, "E001", "`for` needs a loop variable, as in `for i in 1:N`", clause; scope = scope)
        return nothing
    end
    parts = _range_parts(cch[2])
    if parts === nothing
        _error!(
            b,
            "E001",
            "`for` needs a range `1:N`, found `$(_slice(b.text, cch[2]))`";
            scope = scope,
            hint = "`N` must be a `@constants` value",
        )
        return nothing
    end
    lo = _to_expr!(b, parts[1], scope)
    hi = _to_expr!(b, parts[2], scope)
    step = parts[3] === nothing ? nothing : _to_expr!(b, parts[3], scope)
    (lo === nothing || hi === nothing || (parts[3] !== nothing && step === nothing)) &&
        return nothing
    body = _parse_stmt_list!(b, ch[2], scope)
    return ForStatement(var, lo, hi, step, body, rng, scope)
end

# ---------------------------------------------------------------------------------------
# Causality
# ---------------------------------------------------------------------------------------

function _parse_causality!(b::BlockBuilder, node)
    rng = _range(node, b.filename)
    if kind(node) != K"call"
        _error!(
            b,
            "E001",
            "`@causality` takes `p => :effort_out`, `p => (:effort_out, :fixed)` or `(p1, p2) => :transformer`",
        )
        return nothing
    end
    ch = _children(node)
    if !(length(ch) == 3 && _is_operator_node(ch[2]) && _operator_symbol(ch[2]) === Symbol("=>"))
        _error!(b, "E001", "`@causality` entries use `=>`", node)
        return nothing
    end
    port_nodes = kind(ch[1]) == K"tuple" ? _children(ch[1]) : [ch[1]]
    ports = Symbol[]
    for p in port_nodes
        s = _leaf_symbol(p)
        if s === nothing
            _error!(b, "E001", "a causality port must be an identifier", p)
            return nothing
        end
        push!(ports, s)
    end
    rhs = ch[3]
    if kind(rhs) == K"quote"
        v = length(_children(rhs)) == 1 ? _leaf_symbol(_children(rhs)[1]) : nothing
        if length(ports) == 1
            if v === :effort_out || v === :flow_out
                return CausalityDecl(ports, :preferred, v, rng)
            elseif v === :fixed
                _error!(
                    b,
                    "E001",
                    "`fixed` causality needs a direction: `p => (:effort_out, :fixed)`",
                    rhs;
                    hint = "write `p => (:effort_out, :fixed)` or `p => (:flow_out, :fixed)`",
                )
                return nothing
            end
            _error!(
                b,
                "E001",
                "`$v` is not a causality value",
                rhs;
                hint = "use `:effort_out`, `:flow_out`, `(:effort_out, :fixed)` or `(:flow_out, :fixed)`",
            )
            return nothing
        elseif length(ports) == 2
            if v === :transformer || v === :gyrator
                return CausalityDecl(ports, v, nothing, rng)
            end
            _error!(
                b,
                "E001",
                "a two-port causality must be `:transformer` or `:gyrator`",
                rhs;
                hint = "write `(p1, p2) => :transformer`",
            )
            return nothing
        end
        _error!(b, "E001", "a causality entry names at most two ports", node)
        return nothing
    elseif kind(rhs) == K"tuple"
        vals = _children(rhs)
        if length(ports) != 1
            _error!(b, "E001", "a direction and a kind apply to one port, not $(length(ports))", node)
            return nothing
        end
        if length(vals) != 2
            _error!(
                b,
                "E001",
                "a fixed causality is `p => (:effort_out, :fixed)` or `p => (:flow_out, :fixed)`",
                node,
            )
            return nothing
        end
        v = kind(vals[1]) == K"quote" && length(_children(vals[1])) == 1 ?
            _leaf_symbol(_children(vals[1])[1]) : nothing
        k = kind(vals[2]) == K"quote" && length(_children(vals[2])) == 1 ?
            _leaf_symbol(_children(vals[2])[1]) : nothing
        if (v === :effort_out || v === :flow_out) && k === :fixed
            return CausalityDecl(ports, :fixed, v, rng)
        end
        _error!(
            b,
            "E001",
            "a fixed causality is `p => (:effort_out, :fixed)` or `p => (:flow_out, :fixed)`",
            node,
        )
        return nothing
    end
    _error!(b, "E001", "`@causality` needs a symbol value, as in `p => :effort_out`", rhs)
    return nothing
end

# ---------------------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------------------

function _to_expr!(b::BlockBuilder, node, scope::Symbol)
    k = kind(node)
    rng = _range(node, b.filename)

    if k == K"Identifier"
        return Name(node.val, rng)
    elseif k == K"Integer" || k == K"HexInt" || k == K"OctInt" || k == K"BinInt" ||
           k == K"Float"
        return Lit(node.val, rng)
    elseif k == K"Bool"
        return Lit(node.val, rng)
    elseif k == K"Char"
        _error!(b, "E001", "character literals are not allowed", node)
        return nothing
    elseif k == K"String"
        return Lit(String(node.val), rng)
    elseif k == K"string"
        ch = _children(node)
        if length(ch) == 1 && kind(ch[1]) == K"String"
            return Lit(String(ch[1].val), rng)
        end
        _error!(
            b,
            "E001",
            "string interpolation is not allowed";
            hint = "strings only appear in `unit` and `description` attributes",
        )
        return nothing
    elseif k == K"call"
        return _call_to_expr!(b, node, scope)
    elseif k == K"."
        ch = _children(node)
        base = _to_expr!(b, ch[1], scope)
        field = _leaf_symbol(ch[2])
        (base === nothing || field === nothing) && return nothing
        return Field(base, field, rng)
    elseif k == K"ref"
        ch = _children(node)
        base = _to_expr!(b, ch[1], scope)
        base === nothing && return nothing
        idx = Expr[]
        for i in ch[2:end]
            e = _to_expr!(b, i, scope)
            e === nothing && return nothing
            push!(idx, e)
        end
        return Index(base, idx, rng)
    elseif k == K"vect"
        els = Expr[]
        for el in _children(node)
            e = _to_expr!(b, el, scope)
            e === nothing && return nothing
            push!(els, e)
        end
        return VectorLit(els, rng)
    elseif k == K"vcat" || k == K"hcat" || k == K"typed_vcat" || k == K"typed_hcat"
        return _matrix_to_expr!(b, node, scope)
    elseif k == K"&&" || k == K"||"
        op = k == K"&&" ? Symbol("&&") : Symbol("||")
        ops = Expr[]
        for el in _children(node)
            e = _to_expr!(b, el, scope)
            e === nothing && return nothing
            push!(ops, e)
        end
        return BoolOp(op, ops, rng)
    elseif k == K"if"
        _error!(
            b,
            "E001",
            "`if` is only allowed around whole equations, not inside an expression";
            hint = "use `ifelse(cond, a, b)` inside an expression",
        )
        return nothing
    elseif k == K"?"
        _error!(
            b,
            "E001",
            "the `? :` ternary operator is not allowed";
            hint = "use `ifelse(cond, a, b)`",
        )
        return nothing
    elseif k == K"dotcall"
        _error!(
            b,
            "E001",
            "broadcasting with `.` is not allowed";
            hint = "write the operation on the whole array, or use `dot`",
        )
        return nothing
    elseif k == K"comparison"
        _error!(
            b,
            "E001",
            "chained comparisons are not allowed";
            hint = "use one comparison, or combine two with `&&` inside `ifelse`",
        )
        return nothing
    elseif k == K"quote"
        _error!(b, "E001", "symbol literals are only allowed in `state` and `@causality`")
        return nothing
    elseif k == K"macrocall"
        _error!(b, "E001", "macros are not allowed in expressions", node)
        return nothing
    elseif k == K"function" || k == K"do"
        _error!(b, "E001", "function definitions and `do` blocks are not allowed", node)
        return nothing
    elseif k == K"let"
        _error!(b, "E001", "`let` blocks are not allowed", node)
        return nothing
    elseif k == K"curly" || k == K"::" || k == K"where"
        _error!(
            b,
            "E001",
            "a type annotation is only allowed in a declaration";
            hint = "write `name::Type` in the declaration, not in an expression",
        )
        return nothing
    elseif k == K"block"
        _error!(b, "E001", "a `begin ... end` block is not an expression", node)
        return nothing
    elseif k == K"in"
        _error!(b, "E001", "`in` is only allowed in a `for` loop", node)
        return nothing
    end
    _error!(
        b,
        "E001",
        "$(_label(node)) is not allowed in an expression";
        hint = "see the operator table in the language spec",
    )
    return nothing
end

function _call_to_expr!(b::BlockBuilder, node, scope::Symbol)
    ch = _children(node)
    rng = _range(node, b.filename)
    isempty(ch) && return nothing

    # Unary operator: `-x`, `+x`, `!x` (two children, the first an operator token).
    if length(ch) == 2 && _is_operator_node(ch[1])
        op = _operator_symbol(ch[1])
        operand = _to_expr!(b, ch[2], scope)
        operand === nothing && return nothing
        if op === :- || op === :+ || op === Symbol("!")
            return UnOp(op, operand, rng)
        end
        _error!(b, "E001", "unary `$op` is not allowed", node)
        return nothing
    end
    # Infix operator: `a + b`, `a == b`, ... (the middle leaf is an operator token). The
    # operands may be arbitrary expressions, so this must come before the callee check.
    # JuliaSyntax flattens a left-associative chain into one node: `a + b + c` has children
    # [a, +, b, +, c], so the chain is folded left here (it keeps `+`/`-`/`*`/`/` mixed
    # exactly as written).
    if length(ch) >= 3 && _is_operator_node(ch[2])
        op = _operator_symbol(ch[2])
        if is_comparison_op(op) || op === :~ || op === Symbol("=>") ||
           op === Symbol(":") || op === :in || op === :isa
            if length(ch) != 3
                _error!(b, "E001", "operator `$op` takes two operands", node)
                return nothing
            end
            if is_comparison_op(op)
                lhs = _to_expr!(b, ch[1], scope)
                rhs = _to_expr!(b, ch[3], scope)
                (lhs === nothing || rhs === nothing) && return nothing
                return Comparison(op, lhs, rhs, rng)
            elseif op === :~
                _error!(
                    b,
                    "E001",
                    "`~` is only allowed at the top level of an equation";
                    hint = "write `lhs ~ rhs` on its own line",
                )
                return nothing
            elseif op === Symbol("=>")
                _error!(b, "E001", "`=>` is only allowed in `@causality`", node)
                return nothing
            elseif op === Symbol(":")
                _error!(b, "E001", "a range is only allowed in a `for` loop", node)
                return nothing
            end
            _error!(b, "E001", "`$op` is not allowed in an expression", node)
            return nothing
        end
        lhs = _to_expr!(b, ch[1], scope)
        lhs === nothing && return nothing
        if operator_rule_key(op) === nothing
            hint = op === Symbol("%") ? "use `mod(a, b)` or `rem(a, b)`" : nothing
            _error!(b, "E002", "operator `$op` is not on the whitelist", ch[2]; hint = hint)
            return nothing
        end
        # `a + b + c` is one node: [a, +, b, c]. Fold the remaining operands left.
        for j in 3:length(ch)
            rhs = _to_expr!(b, ch[j], scope)
            rhs === nothing && return nothing
            lhs = BinOp(op, lhs, rhs, rng)
        end
        return lhs
    end
    # A function call: the callee must be a name.
    fname = _leaf_symbol(ch[1])
    if fname === nothing
        _error!(b, "E001", "a call must start with a function name", ch[1])
        return nothing
    end
    # Zero-argument call: `f()` has only the callee as a child.
    if length(ch) == 1
        return Call(Name(fname, _range(ch[1], b.filename)), Expr[], rng)
    end
    args = Expr[]
    for a in ch[2:end]
        e = _to_expr!(b, a, scope)
        e === nothing && return nothing
        push!(args, e)
    end
    callee = Name(fname, _range(ch[1], b.filename))
    if fname === :ifelse
        if length(args) == 3
            return IfElse(args[1], args[2], args[3], rng)
        end
        _error!(
            b,
            "E001",
            "`ifelse` takes 3 arguments, got $(length(args))";
            hint = "write `ifelse(cond, a, b)`",
        )
        return nothing
    end
    return Call(callee, args, rng)
end

function _matrix_to_expr!(b::BlockBuilder, node, scope::Symbol)
    rng = _range(node, b.filename)
    k = kind(node)
    if k == K"typed_vcat" || k == K"typed_hcat"
        _error!(
            b,
            "E001",
            "a typed array literal is not allowed";
            hint = "write the literal and declare the type: `p::Mat{2,2} = [1 0; 0 1]`",
        )
        return nothing
    end
    rows = Vector{Vector{Expr}}()
    if k == K"hcat"
        row = Expr[]
        for el in _children(node)
            e = _to_expr!(b, el, scope)
            e === nothing && return nothing
            push!(row, e)
        end
        push!(rows, row)
    else
        for r in _children(node)
            if kind(r) == K"row"
                row = Expr[]
                for el in _children(r)
                    e = _to_expr!(b, el, scope)
                    e === nothing && return nothing
                    push!(row, e)
                end
                push!(rows, row)
            else
                e = _to_expr!(b, r, scope)
                e === nothing && return nothing
                push!(rows, Expr[e])
            end
        end
    end
    if isempty(rows)
        _error!(b, "E005", "an array literal needs at least one element", node)
        return nothing
    end
    n = length(rows[1])
    for row in rows
        if length(row) != n
            _error!(
                b,
                "E005",
                "matrix literal rows must all have the same length ($(n) and $(length(row)))",
                node,
            )
            return nothing
        end
    end
    return MatrixLit(rows, rng)
end

# ---------------------------------------------------------------------------------------
# Finalisation: attribute folding and `structural` inference
# ---------------------------------------------------------------------------------------

function _finalize_block!(b::BlockBuilder)
    env = _constant_env(b.declaration_map)
    _collect_structural_refs!(b)
    for scope in DECLARATION_SCOPES
        for decl in b.declaration_map[scope]
            for key in (:min, :max, :nominal)
                haskey(decl.attrs, key) || continue
                v = decl.attrs[key]
                v isa Expr || continue
                n = eval_const_number(v, env)
                if n === nothing
                    _error!(
                        b,
                        "E004",
                        "`$key` must be a numeric constant";
                        hint = "write a number, or a `@constants` expression",
                    )
                    delete!(decl.attrs, key)
                else
                    decl.attrs[key] = n
                end
            end
            if scope == :constants
                # A constant that sets an array size is structural even if the attribute is
                # omitted (plan 4.3: "structural (constants only, implied)").
                inferred = decl.name in b.size_refs
                explicit = get(decl.attrs, :structural, false) === true
                decl.attrs[:structural] = inferred || explicit
            end
        end
    end
    _fold_discrete_clocks!(b, env)
    return nothing
end

# A constant used in a `for` bound or a `@discrete` clock is structural too: overriding it
# changes the unrolled code, so the catalog must mark it (decision D13). Add those names to
# `size_refs`, which is what the `:structural` inference below consults.
# A constant used in a `for` bound or a `@discrete` clock is structural: overriding it
# changes the unrolled code, so the catalog must mark it (decision D13). Add those names to
# `size_refs`, which is what the `:structural` inference below consults.
function _collect_structural_refs!(b::BlockBuilder)
    found = Set{Symbol}()
    for item in b.equation_items
        _collect_for_bounds!(found, item)
    end
    for item in b.initial_items
        _collect_for_bounds!(found, item)
    end
    for ds in b.discrete_items
        _collect_expr_refs!(found, ds.period)
        ds.offset === nothing || _collect_expr_refs!(found, ds.offset)
        for stmt in ds.body
            _collect_for_bounds!(found, stmt)
        end
    end
    for ev in b.event_items
        for stmt in ev.body
            _collect_for_bounds!(found, stmt)
        end
    end
    constant_names = Set(decl.name for decl in get(b.declaration_map, :constants, Decl[]))
    for name in intersect(found, constant_names)
        push!(b.size_refs, name)
    end
    return nothing
end

function _collect_for_bounds!(found::Set{Symbol}, item)
    if item isa IfEquation
        for branch in item.branches, sub in branch.body
            _collect_for_bounds!(found, sub)
        end
    elseif item isa ForEquation
        for e in (item.lo, item.hi, item.step)
            e === nothing || _collect_expr_refs!(found, e)
        end
        for sub in item.body
            _collect_for_bounds!(found, sub)
        end
    elseif item isa IfStatement
        for branch in item.branches, sub in branch.body
            _collect_for_bounds!(found, sub)
        end
    elseif item isa ForStatement
        for e in (item.lo, item.hi, item.step)
            e === nothing || _collect_expr_refs!(found, e)
        end
        for sub in item.body
            _collect_for_bounds!(found, sub)
        end
    end
    return nothing
end

_collect_expr_refs!(found::Set{Symbol}, e::Name) = (push!(found, e.name); nothing)
_collect_expr_refs!(::Set{Symbol}, ::Lit) = nothing
function _collect_expr_refs!(found::Set{Symbol}, e::Field)
    _collect_expr_refs!(found, e.base)
end
function _collect_expr_refs!(found::Set{Symbol}, e::Call)
    for a in e.args
        _collect_expr_refs!(found, a)
    end
end
function _collect_expr_refs!(found::Set{Symbol}, e::BinOp)
    _collect_expr_refs!(found, e.lhs)
    _collect_expr_refs!(found, e.rhs)
end
function _collect_expr_refs!(found::Set{Symbol}, e::UnOp)
    _collect_expr_refs!(found, e.operand)
end
function _collect_expr_refs!(found::Set{Symbol}, e::Index)
    _collect_expr_refs!(found, e.base)
    for i in e.indices
        _collect_expr_refs!(found, i)
    end
end
function _collect_expr_refs!(found::Set{Symbol}, e::VectorLit)
    for a in e.elements
        _collect_expr_refs!(found, a)
    end
end
function _collect_expr_refs!(found::Set{Symbol}, e::MatrixLit)
    for row in e.rows, a in row
        _collect_expr_refs!(found, a)
    end
end
function _collect_expr_refs!(found::Set{Symbol}, e::IfElse)
    _collect_expr_refs!(found, e.cond)
    _collect_expr_refs!(found, e.then)
    _collect_expr_refs!(found, e.otherwise)
end
function _collect_expr_refs!(found::Set{Symbol}, e::Comparison)
    _collect_expr_refs!(found, e.lhs)
    _collect_expr_refs!(found, e.rhs)
end
function _collect_expr_refs!(found::Set{Symbol}, e::BoolOp)
    for a in e.operands
        _collect_expr_refs!(found, a)
    end
end

"""Fold every `@discrete` period and offset once all constants are known (plan 5.9: the
period is a constant expression). A period that does not fold, is not a number or is not
positive is E004; an offset outside `0 <= offset < Ts` is E004 too."""
function _fold_discrete_clocks!(b::BlockBuilder, env::AbstractDict)
    for (i, ds) in enumerate(b.discrete_items)
        period = _fold_clock!(b, ds.period, "period", env; positive = true)
        offset = nothing
        if ds.offset !== nothing
            offset = _fold_clock!(b, ds.offset, "offset", env; positive = false)
            if offset !== nothing && period !== nothing && !(offset < period)
                _error!(
                    b,
                    "E004",
                    "the `@discrete` offset ($offset) must be smaller than its period ($period)",
                    ds.offset;
                    scope = :discrete,
                    hint = "write an offset in `0 <= offset < Ts`",
                )
                offset = nothing
            end
        end
        b.discrete_items[i] = DiscreteScope(
            ds.period, ds.offset, ds.body, ds.range, period, offset
        )
    end
    return nothing
end

function _fold_clock!(b::BlockBuilder, e, what::String, env::AbstractDict; positive::Bool)
    ok, value = try_eval_const(e, env)
    if !ok
        _error!(
            b,
            "E004",
            "the `@discrete` $what must be a constant expression: $value",
            e;
            scope = :discrete,
            hint = "use a real literal or a `@constants` value",
        )
        return nothing
    end
    if !(value isa Real) || value isa Bool
        _error!(
            b,
            "E004",
            "the `@discrete` $what must be a real number",
            e;
            scope = :discrete,
        )
        return nothing
    end
    if positive && !(value > 0)
        _error!(
            b,
            "E004",
            "the `@discrete` period must be positive, got $value",
            e;
            scope = :discrete,
        )
        return nothing
    end
    if !positive && value < 0
        _error!(
            b,
            "E004",
            "the `@discrete` offset must not be negative, got $value",
            e;
            scope = :discrete,
        )
        return nothing
    end
    return Float64(value)
end

"""
    constant_env(decl_map) -> Dict{Symbol,Any}

The value of every `@constants` entry, folded in dependency order (a constant may use
another constant). Unfoldable constants are left out; `check_block` reports them.
"""
function _constant_env(declaration_map::AbstractDict)
    env = Dict{Symbol,Any}()
    pending = collect(get(declaration_map, :constants, Decl[]))
    for _ in 1:(length(pending) + 1)
        isempty(pending) && break
        progress = false
        rest = Decl[]
        for d in pending
            if d.default === nothing
                push!(rest, d)
                continue
            end
            ok, v = try_eval_const(d.default, env)
            if ok
                env[d.name] = v
                progress = true
            else
                push!(rest, d)
            end
        end
        pending = rest
        progress || break
    end
    return env
end

"""    constant_env(pb::ParsedBlock) -> Dict{Symbol,Any}

The folded `@constants` values of a block. Used by `block_interface` and by the balance check
(a `Vec{N}` size is resolved from here)."""
constant_env(pb::ParsedBlock) = _constant_env(pb.declaration_map)
