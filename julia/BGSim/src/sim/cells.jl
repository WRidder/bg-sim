# The code cells of the modelling assistant (plan/ASSISTANT_PLAN.md): Julia-syntax scripts over a
# run and its model, for any derived quantity, table or plot.
#
# A cell obeys the language's rule (spec, design principle 2): Julia syntax, not Julia semantics.
# The text is parsed with the front end and interpreted here over our own AST; it is never
# `eval`ed, so a cell has no I/O, no packages and no way out of these files. It is more than an
# expression, though: assignments, `for`, `while`, `if`, helper functions, tuples, vectors,
# matrices and complex numbers, with the numeric library of `cell_library.jl`. A work budget and
# a call depth bound what it can burn.
#
#   t               the run's time vector
#   s"Load/w"       a recorded signal as a vector, or a block parameter (`s"Motor/R"`) as a number
#   Kp              a global parameter of the model, or a variable of the cell
#
# `*`, `/` and `^` on two vectors are elementwise; with a matrix they are matrix operations, and
# the dotted forms are always elementwise. The model is compiled only when a cell reads a
# parameter. The output goes to the chat: `plot`, `scatter`, `bar`, `table`, `image` and `text`
# (capitalised too, and the title is optional), and each bare top-level expression is shown like
# a REPL line.

const CELL_WORK_LIMIT = 500_000_000  # elements touched by one cell
const CELL_TIME_LIMIT_S = 30.0
const CELL_MAX_DEPTH = 200
const CELL_MAX_POINTS = 2000
const CELL_MAX_ROWS = 200
const CELL_MAX_LINES = 200
const CELL_MAX_IMAGE = 400

# The output statements, as written in a cell.
const CELL_OUTPUTS = Dict(
    :plot => :plot, :Plot => :plot, :scatter => :scatter, :Scatter => :scatter, :bar => :bar,
    :Bar => :bar, :table => :table, :Table => :table, :image => :image, :Image => :image,
    :text => :text, :Text => :text, :print => :text, :println => :text,
)

abstract type CellStmt end

struct CellSet <: CellStmt
    name::Symbol
    op::Symbol  # :assign, or the operator of a compound assignment
    value::Expr
    range::SourceRange
end

struct CellSetAt <: CellStmt
    name::Symbol
    indices::Vector{Expr}
    value::Expr
    range::SourceRange
end

struct CellUnpack <: CellStmt
    names::Vector{Symbol}
    value::Expr
    range::SourceRange
end

struct CellFor <: CellStmt
    var::Symbol
    over::Expr
    body::Vector{CellStmt}
    range::SourceRange
end

struct CellWhile <: CellStmt
    cond::Expr
    body::Vector{CellStmt}
    range::SourceRange
end

struct CellIf <: CellStmt
    branches::Vector{Tuple{Expr,Vector{CellStmt}}}  # a `true` literal condition is the `else`
    range::SourceRange
end

struct CellShow <: CellStmt
    text::String
    value::Expr
    range::SourceRange
end

struct CellFigure <: CellStmt
    kind::Symbol  # a value of CELL_OUTPUTS
    title::String
    labels::Vector{String}
    args::Vector{Expr}
    range::SourceRange
end

struct CellDef <: CellStmt
    name::Symbol
    params::Vector{Symbol}
    body::Vector{CellStmt}
    range::SourceRange
end

struct CellReturn <: CellStmt
    value::Union{Expr,Nothing}
    range::SourceRange
end

struct CellJump <: CellStmt
    kind::Symbol  # :break, :continue
    range::SourceRange
end

mutable struct CellRun
    env::Dict{Symbol,Any}
    top::Dict{Symbol,Any}
    functions::Dict{Symbol,CellDef}
    signal::Function   # id -> value
    name::Function     # bare name -> value or nothing
    output::Vector{String}
    figures::Vector{Any}
    budget::Int
    deadline::UInt64
    depth::Int
    returned::Any
end

struct CellText <: CellStmt
    parts::Vector{Any}  # String, or an Expr to show
    range::SourceRange
end

# ---------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------

_cell_text(node) = strip(JuliaSyntax.sourcetext(node))

function _cell_exprs!(b::_WatchBuilder, nodes)
    out = Expr[]
    for node in nodes
        e = _watch_to_expr!(b, node)
        e === nothing && return nothing
        push!(out, e)
    end
    return out
end

function _cell_array!(b::_WatchBuilder, node)
    k = kind(node)
    rng = _range(node, b.filename)
    ch = _children(node)
    if k == K"ref"
        items = _cell_exprs!(b, ch)
        items === nothing && return nothing
        return Index(items[1], items[2:end], rng)
    elseif k == K"vect"
        items = _cell_exprs!(b, ch)
        return items === nothing ? nothing : VectorLit(items, rng)
    elseif k == K"hcat"
        items = _cell_exprs!(b, ch)
        return items === nothing ? nothing : MatrixLit([items], rng)
    end
    rows = Vector{Expr}[]  # K"vcat": rows of a matrix, or the elements of `[1; 2]`
    for row in ch
        items = _cell_exprs!(b, kind(row) == K"row" ? _children(row) : [row])
        items === nothing && return nothing
        push!(rows, items)
    end
    return MatrixLit(rows, rng)
end

_cell_literal(node) = String(strip(_cell_text(node), '"'))

function _cell_output!(b::_WatchBuilder, node, written::Symbol)
    what = CELL_OUTPUTS[written]
    ch = _children(node)[2:end]
    rng = _range(node, b.filename)
    if what === :text
        parts = Any[]
        for a in ch
            e = kind(a) == K"string" ? _cell_literal(a) : _watch_to_expr!(b, a)
            e === nothing && return nothing
            push!(parts, e)
        end
        return CellText(parts, rng)
    end
    title = !isempty(ch) && kind(ch[1]) == K"string" ? _cell_literal(ch[1]) : nothing
    values = title === nothing ? ch : ch[2:end]
    needed = what === :table || what === :image ? 1 : 2
    if length(values) < needed
        _werr!(b, "E001", "`$written` needs at least $needed values", rng;
            hint = "write `$written(\"Title\", ...)`; the title is optional")
        return nothing
    end
    args = _cell_exprs!(b, values)
    args === nothing && return nothing
    labels = String[String(_cell_text(a)) for a in values]
    return CellFigure(what, something(title, ""), labels, args, rng)
end

function _cell_body!(b::_WatchBuilder, node)
    out = CellStmt[]
    for stmt in (kind(node) == K"block" ? _children(node) : [node])
        parsed = _cell_stmt!(b, stmt)
        parsed === nothing || push!(out, parsed)
    end
    return out
end

function _cell_if!(b::_WatchBuilder, node, branches)
    ch = _children(node)
    cond = _watch_to_expr!(b, ch[1])
    cond === nothing && return nothing
    push!(branches, (cond, _cell_body!(b, ch[2])))
    for rest in ch[3:end]
        if kind(rest) == K"elseif"
            _cell_if!(b, rest, branches)
        else
            push!(branches, (Lit(true, _range(rest, b.filename)), _cell_body!(b, rest)))
        end
    end
    return nothing
end

function _cell_signature(b::_WatchBuilder, signature)
    rng = _range(signature, b.filename)
    if kind(signature) != K"call"
        _werr!(b, "E001", "a function is `name(a, b)`", rng)
        return nothing
    end
    ch = _children(signature)
    name = _leaf_symbol(ch[1])
    params = Symbol[]
    for a in ch[2:end]
        if kind(a) != K"Identifier"
            _werr!(b, "E001", "function arguments are plain names", _range(a, b.filename))
            return nothing
        end
        push!(params, a.val)
    end
    if name === nothing || haskey(CELL_OUTPUTS, name)
        _werr!(b, "E001", "that is not a function name", rng)
        return nothing
    end
    return name, params
end

function _cell_def!(b::_WatchBuilder, node)
    ch = _children(node)
    signature = _cell_signature(b, ch[1])
    signature === nothing && return nothing
    rng = _range(node, b.filename)
    return CellDef(signature[1], signature[2], _cell_body!(b, ch[2]), rng)
end

function _cell_assign!(b::_WatchBuilder, node, rng)
    ch = _children(node)
    target = ch[1]
    if kind(target) == K"call"  # `f(x) = x^2`
        signature = _cell_signature(b, target)
        signature === nothing && return nothing
        return CellDef(signature[1], signature[2], _cell_body!(b, ch[2]), rng)
    end
    value = _watch_to_expr!(b, ch[2])
    value === nothing && return nothing
    if kind(target) == K"Identifier"
        return CellSet(target.val, :assign, value, rng)
    elseif kind(target) == K"tuple" && all(n -> kind(n) == K"Identifier", _children(target))
        return CellUnpack(Symbol[n.val for n in _children(target)], value, rng)
    elseif kind(target) == K"ref" && kind(_children(target)[1]) == K"Identifier"
        indices = _cell_exprs!(b, _children(target)[2:end])
        indices === nothing && return nothing
        return CellSetAt(_children(target)[1].val, indices, value, rng)
    end
    _werr!(b, "E001", "assign to a name, to `a, b` or to `v[i]`", rng)
    return nothing
end

function _cell_stmt!(b::_WatchBuilder, node)
    k = kind(node)
    rng = _range(node, b.filename)
    if k == K"="
        return _cell_assign!(b, node, rng)
    elseif k == K"op="
        ch = _children(node)
        op = _operator_symbol(ch[2])
        value = _watch_to_expr!(b, ch[3])
        value === nothing && return nothing
        if kind(ch[1]) == K"Identifier" && op in (:+, :-, :*, :/)
            return CellSet(ch[1].val, op, value, rng)
        end
        _werr!(b, "E001", "a compound assignment is `name += value`", rng)
        return nothing
    elseif k == K"for"
        ch = _children(node)
        iter = _children(ch[1])
        parts = length(iter) == 1 ? _children(iter[1]) : []
        if length(parts) != 2 || kind(parts[1]) != K"Identifier"
            _werr!(b, "E001", "`for` takes one range, as in `for i in 1:N`", rng)
            return nothing
        end
        over = _watch_to_expr!(b, parts[2])
        over === nothing && return nothing
        return CellFor(parts[1].val, over, _cell_body!(b, ch[2]), rng)
    elseif k == K"while"
        ch = _children(node)
        cond = _watch_to_expr!(b, ch[1])
        cond === nothing && return nothing
        return CellWhile(cond, _cell_body!(b, ch[2]), rng)
    elseif k == K"if"
        branches = Tuple{Expr,Vector{CellStmt}}[]
        _cell_if!(b, node, branches)
        return CellIf(branches, rng)
    elseif k == K"function"
        return _cell_def!(b, node)
    elseif k == K"return"
        ch = _children(node)
        isempty(ch) && return CellReturn(nothing, rng)
        value = _watch_to_expr!(b, ch[1])
        return value === nothing ? nothing : CellReturn(value, rng)
    elseif k == K"break"
        return CellJump(:break, rng)
    elseif k == K"continue"
        return CellJump(:continue, rng)
    elseif k == K"macro" || k == K"struct" || k == K"using" || k == K"import" || k == K"try" ||
           k == K"let" || k == K"module" || k == K"quote" || k == K"global" || k == K"const"
        _werr!(b, "E001", "$(_label(node)) is not allowed in a cell", rng;
            hint = "a cell has assignments, loops, `if`, functions, `plot`, `table` and expressions")
        return nothing
    elseif k == K"call" && !isempty(_children(node)) &&
           haskey(CELL_OUTPUTS, _leaf_symbol(_children(node)[1]))
        return _cell_output!(b, node, _leaf_symbol(_children(node)[1]))
    end
    value = _watch_to_expr!(b, node)
    return value === nothing ? nothing : CellShow(String(_cell_text(node)), value, rng)
end

"""
    parse_cell(text) -> (statements, diagnostics)

A cell as statements, or `nothing` with E001 diagnostics (`scope = "watch"`)."""
function parse_cell(text::AbstractString)
    src = String(text)
    b = _WatchBuilder(Diagnostic[], "cell", true)
    tree = try
        JuliaSyntax.parseall(
            SyntaxNode, src; filename = "cell", ignore_errors = false, ignore_warnings = true
        )
    catch err
        err isa JuliaSyntax.ParseError || rethrow()
        for d in err.diagnostics
            d.level === :error || continue
            r = _range(err.source, d.first_byte, d.last_byte, "cell")
            _werr!(b, "E001", "syntax error: " * lowercasefirst(d.message), r)
        end
        return nothing, b.diagnostics
    end
    statements = CellStmt[]
    for node in _children(tree)
        parsed = _cell_stmt!(b, node)
        parsed === nothing || push!(statements, parsed)
    end
    return (isempty(b.diagnostics) ? statements : nothing), b.diagnostics
end

# ---------------------------------------------------------------------------------------
# Evaluating
# ---------------------------------------------------------------------------------------

_cell_len(v) = v isa AbstractArray ? length(v) : 1

function _cell_spend!(r::CellRun, n::Integer)
    r.budget -= n
    (r.budget < 0 || time_ns() > r.deadline) && _cell_fail("the cell exceeded its work limit")
    return nothing
end

function _cell_lift(r::CellRun, f, args...)
    arrays = [a for a in args if a isa AbstractArray]
    isempty(arrays) && return f(args...)
    all(a -> size(a) == size(arrays[1]), arrays) ||
        _cell_fail("arrays of different sizes: " * join((length(a) for a in arrays), " and "))
    _cell_spend!(r, length(arrays[1]))
    return broadcast(f, args...)
end

function _cell_range(r::CellRun, args)
    all(a -> a isa Real, args) || _cell_fail("a range is made of numbers")
    v = length(args) == 2 ? (args[1]:args[2]) : (args[1]:args[2]:args[3])
    _cell_spend!(r, length(v))
    return collect(v)
end

_cell_is_matrix(a) = a isa AbstractMatrix

function _cell_binop(r::CellRun, op::Symbol, a, b)
    if op === :\
        _cell_spend!(r, length(b)^2)
        return _cell_solve(a, b)
    elseif _cell_is_matrix(a) || _cell_is_matrix(b)
        _cell_spend!(r, _cell_len(a) * max(1, _cell_len(b)))
        try
            op === :* && return a * b
            op === :/ && return a / b
            op === :^ && return a^b
        catch err
            err isa DimensionMismatch || rethrow()
            _cell_fail("the sizes do not fit: $(size(a)) and $(size(b))")
        end
    end
    op === :+ && return _cell_lift(r, +, a, b)
    op === :- && return _cell_lift(r, -, a, b)
    op === :* && return _cell_lift(r, *, a, b)
    op === :/ && return _cell_lift(r, /, a, b)
    op === :^ && return _cell_lift(r, ^, a, b)
    _cell_fail("operator `$op` is not allowed in a cell")
end

function _cell_compare(op::Symbol)
    op === :< && return <
    op === :<= && return <=
    op === :> && return >
    op === :>= && return >=
    op === Symbol("==") && return ==
    op === Symbol("!=") && return !=
    _cell_fail("unknown comparison `$op`")
end

const _CELL_ALL = :all_of_this_dimension

function _cell_position(index, n::Int)
    index === _CELL_ALL && return 1:n
    if index isa AbstractVector
        if eltype(index) <: Bool
            length(index) == n || _cell_fail("a mask must have the length of its dimension")
            return findall(index)
        end
        return Int[_cell_position(i, n) for i in index]
    end
    index isa Real && !(index isa Bool) && isinteger(index) || _cell_fail("an index is a whole number")
    i = Int(index)
    1 <= i <= n || _cell_fail("index $i is out of range for a length of $n")
    return i
end

function _cell_index(r::CellRun, e::Index)
    base = _cell_value(e.base, r)
    base isa AbstractArray || base isa Tuple || _cell_fail("cannot index a scalar")
    base isa Tuple && (base = collect(base))
    count = length(e.indices)
    (count == 1 || (count == 2 && base isa AbstractMatrix)) ||
        _cell_fail("wrong number of indices: $count")
    outer = get(r.env, :end, nothing)
    positions = Any[]
    for (dim, index) in enumerate(e.indices)
        n = count == 1 ? length(base) : size(base, dim)
        r.env[:end] = n
        push!(positions, _cell_position(_cell_value(index, r), n))
    end
    outer === nothing ? delete!(r.env, :end) : (r.env[:end] = outer)
    picked = base[positions...]
    _cell_spend!(r, _cell_len(picked))
    return picked
end

function _cell_call_function(r::CellRun, f::CellDef, args::Vector{Any})
    length(args) == length(f.params) ||
        _cell_fail("`$(f.name)` takes $(length(f.params)) arguments, got $(length(args))")
    r.depth >= CELL_MAX_DEPTH && _cell_fail("the calls of `$(f.name)` go too deep")
    outer = r.env
    r.env = Dict{Symbol,Any}(zip(f.params, args))
    r.depth += 1
    try
        for (i, s) in enumerate(f.body)
            if i == length(f.body) && s isa CellShow  # the value of the last expression
                return _cell_value(s.value, r)
            end
            flow = _cell_exec!(s, r)
            if flow === :return
                value = r.returned
                r.returned = nothing
                return value
            end
        end
        return nothing
    finally
        r.env = outer
        r.depth -= 1
    end
end

function _cell_call(r::CellRun, fn::Symbol, args::Vector{Any})
    haskey(r.functions, fn) && return _cell_call_function(r, r.functions[fn], args)
    _cell_spend!(r, isempty(args) ? 1 : max(1, maximum(_cell_len, args)))
    n = length(args)
    fn === :range && n in (2, 3) && return _cell_range(r, args)
    fn === :tuple && return Tuple(args)
    if fn === :zeros || fn === :ones
        n == 1 || _cell_fail("`$fn` takes a length")
        count = _cell_size(args[1])
        _cell_spend!(r, count)
        return fn === :zeros ? zeros(count) : ones(count)
    elseif fn === :linspace
        n == 3 || _cell_fail("`linspace` takes a start, a stop and a count")
        count = _cell_size(args[3])
        _cell_spend!(r, count)
        return collect(range(args[1], args[2]; length = count))
    end
    text = String(fn)
    if startswith(text, ".") && n == 2  # a dotted operator: always elementwise
        op = Symbol(text[2:end])
        op === :+ && return _cell_lift(r, +, args...)
        op === :- && return _cell_lift(r, -, args...)
        op === :* && return _cell_lift(r, *, args...)
        op === :/ && return _cell_lift(r, /, args...)
        op === :^ && return _cell_lift(r, ^, args...)
    end
    entry = get(CELL_LIBRARY, fn, nothing)
    if entry !== nothing
        n in entry[1] || _cell_fail("`$fn` takes $(entry[1]) arguments, got $n")
        return entry[2](args...)
    end
    return _cell_lift(r, (xs...) -> _fold_call(fn, Any[xs...]), args...)
end

_cell_flat(values) = identity.(values)  # the narrowest element type

function _cell_value(e::Expr, r::CellRun)
    if e isa Lit
        return e.value
    elseif e isa Name
        e.name === :(:) && return _CELL_ALL
        haskey(r.env, e.name) && return r.env[e.name]
        haskey(r.top, e.name) && return r.top[e.name]
        e.name === :pi && return Float64(pi)
        e.name === :Inf && return Inf
        e.name === :NaN && return NaN
        e.name === :im && return im
        value = r.name(e.name)
        value === nothing && _cell_fail("`$(e.name)` is not defined")
        return value
    elseif e isa SignalRef
        return r.signal(e.id)
    elseif e isa BinOp
        return _cell_binop(r, e.op, _cell_value(e.lhs, r), _cell_value(e.rhs, r))
    elseif e isa UnOp
        a = _cell_value(e.operand, r)
        e.op === :- && return _cell_lift(r, -, a)
        e.op === :+ && return a
        e.op === Symbol("!") && return _cell_lift(r, !, a)
    elseif e isa Comparison
        return _cell_lift(r, _cell_compare(e.op), _cell_value(e.lhs, r), _cell_value(e.rhs, r))
    elseif e isa BoolOp
        scalar_and = e.op === Symbol("&&")
        result = _cell_value(e.operands[1], r)
        for x in e.operands[2:end]
            if result isa Bool  # short circuit, as Julia does
                (scalar_and ? !result : result) && return result
                result = _cell_value(x, r)
            else
                result = _cell_lift(r, scalar_and ? (&) : (|), result, _cell_value(x, r))
            end
        end
        return result
    elseif e isa IfElse
        cond = _cell_value(e.cond, r)
        cond isa Bool && return _cell_value(cond ? e.then : e.otherwise, r)
        return _cell_lift(r, ifelse, cond, _cell_value(e.then, r), _cell_value(e.otherwise, r))
    elseif e isa Index
        return _cell_index(r, e)
    elseif e isa VectorLit
        _cell_spend!(r, length(e.elements))
        return _cell_flat(Any[_cell_value(x, r) for x in e.elements])
    elseif e isa MatrixLit
        rows = [Any[_cell_value(x, r) for x in row] for row in e.rows]
        n = length(rows[1])
        all(row -> length(row) == n, rows) || _cell_fail("matrix rows must have the same length")
        all(row -> all(x -> x isa Number, row), rows) ||
            return _cell_stack(Any[_cell_stack(row, true) for row in rows], false)
        _cell_spend!(r, n * length(rows))
        return _cell_flat(permutedims(reduce(hcat, rows)))
    elseif e isa Call
        args = Any[_cell_value(a, r) for a in e.args]
        return _cell_call(r, e.fn.name, args)
    end
    _cell_fail("this expression is not allowed in a cell")
end

_cell_json(v::Bool) = v
_cell_json(v::Integer) = v
_cell_json(v::Real) = isfinite(v) ? Float64(v) : nothing
_cell_json(::Complex) = _cell_fail("complex values: use abs(...), real(...) or angle(...)")
_cell_json(::Any) = _cell_fail("a figure takes numbers")

function _cell_number(v)
    v isa Bool && return string(v)
    v isa Integer && return string(v)
    if v isa Complex
        return "$(_cell_number(real(v))) + $(_cell_number(imag(v)))im"
    end
    return string(round(Float64(v); sigdigits = 6))
end

function _cell_show(v)
    v === nothing && return "nothing"
    v isa Tuple && return "(" * join(map(_cell_show, v), ", ") * ")"
    if v isa AbstractMatrix
        return "$(size(v, 1))×$(size(v, 2)) matrix"
    elseif v isa AbstractVector
        head = join((_cell_number(x) for x in v[1:min(end, 8)]), ", ")
        return "[$head$(length(v) > 8 ? ", ..." : "")] ($(length(v)) values)"
    end
    return _cell_number(v)
end

const _CELL_STYLES = Dict(:plot => "line", :scatter => "points", :bar => "bar")

function _cell_plot!(r::CellRun, s::CellFigure)
    values = Any[_cell_value(a, r) for a in s.args]
    x = values[1]
    x isa AbstractVector || _cell_fail("the x of a plot is a vector")
    for (label, y) in zip(s.labels[2:end], values[2:end])
        (y isa AbstractVector && length(y) == length(x)) ||
            _cell_fail("`$label` does not have the length of `$(s.labels[1])`")
    end
    keep = 1:max(1, ceil(Int, length(x) / CELL_MAX_POINTS)):length(x)
    push!(r.figures, (
        kind = "chart", title = s.title, xLabel = s.labels[1], style = _CELL_STYLES[s.kind],
        x = Float64[Float64(real(x[i])) for i in keep],
        series = Any[
            (name = label, y = Any[_cell_json(y[i]) for i in keep])
            for (label, y) in zip(s.labels[2:end], values[2:end])
        ],
    ))
    return nothing
end

function _cell_table!(r::CellRun, s::CellFigure)
    values = Any[_cell_value(a, r) for a in s.args]
    n = maximum(_cell_len, values)
    all(v -> !(v isa AbstractArray) || length(v) == n, values) ||
        _cell_fail("the columns of a table have different lengths")
    cell(v, i) = _cell_json(v isa AbstractArray ? v[i] : v)
    rows = Any[Any[cell(v, i) for v in values] for i in 1:min(n, CELL_MAX_ROWS)]
    push!(r.figures, (
        kind = "table", title = s.title, columns = s.labels, rows = rows,
        truncated = n > CELL_MAX_ROWS,
    ))
    return nothing
end

function _cell_image!(r::CellRun, s::CellFigure)
    M = _cell_value(s.args[1], r)
    M isa AbstractMatrix || _cell_fail("`image` shows a matrix")
    eltype(M) <: Complex && _cell_fail("complex values: use abs(...), real(...) or angle(...)")
    rows = 1:max(1, ceil(Int, size(M, 1) / CELL_MAX_IMAGE)):size(M, 1)
    columns = 1:max(1, ceil(Int, size(M, 2) / CELL_MAX_IMAGE)):size(M, 2)
    picked = Any[Any[_cell_json(M[i, j]) for j in columns] for i in rows]
    finite = Float64[v for row in picked for v in row if v isa Real]
    push!(r.figures, (
        kind = "image", title = s.title, rows = picked,
        min = isempty(finite) ? 0.0 : minimum(finite), max = isempty(finite) ? 1.0 : maximum(finite),
    ))
    return nothing
end

# Each statement returns how control goes on: `nothing`, :break, :continue or :return.
function _cell_exec!(statements::Vector{CellStmt}, r::CellRun)
    for s in statements
        flow = _cell_exec!(s, r)
        flow === nothing || return flow
    end
    return nothing
end

function _cell_exec!(s::CellShow, r::CellRun)
    value = _cell_value(s.value, r)
    length(r.output) < CELL_MAX_LINES && push!(r.output, "$(s.text) = $(_cell_show(value))")
    return nothing
end

function _cell_exec!(s::CellSet, r::CellRun)
    value = _cell_value(s.value, r)
    if s.op !== :assign
        haskey(r.env, s.name) || _cell_fail("`$(s.name)` is not defined")
        value = _cell_binop(r, s.op, r.env[s.name], value)
    end
    r.env[s.name] = value
    return nothing
end

function _cell_exec!(s::CellUnpack, r::CellRun)
    value = _cell_value(s.value, r)
    (value isa Tuple && length(value) == length(s.names)) ||
        _cell_fail("expected $(length(s.names)) values")
    for (name, v) in zip(s.names, value)
        r.env[name] = v
    end
    return nothing
end

function _cell_exec!(s::CellSetAt, r::CellRun)
    base = get(r.env, s.name, nothing)
    base isa AbstractArray || _cell_fail("`$(s.name)` is not an array")
    length(s.indices) == ndims(base) || _cell_fail("`$(s.name)` takes $(ndims(base)) indices")
    positions = Any[
        _cell_position(_cell_value(index, r), size(base, dim)) for (dim, index) in enumerate(s.indices)
    ]
    value = _cell_value(s.value, r)
    value isa Number || _cell_fail("an element takes one number")
    if !(typeof(value) <: eltype(base))  # an Int vector given a Float, like a new binding
        base = r.env[s.name] = Array{promote_type(eltype(base), typeof(value))}(base)
    end
    all(p -> p isa Integer, positions) || _cell_fail("`v[i] = x` takes whole number indices")
    base[positions...] = value
    return nothing
end

function _cell_exec!(s::CellFor, r::CellRun)
    over = _cell_value(s.over, r)
    over isa AbstractVector || _cell_fail("`for` runs over a range or a vector")
    for item in over
        _cell_spend!(r, 1)
        r.env[s.var] = item
        flow = _cell_exec!(s.body, r)
        flow === :break && break
        flow === :return && return flow
    end
    return nothing
end

function _cell_exec!(s::CellWhile, r::CellRun)
    while true
        _cell_spend!(r, 1)
        cond = _cell_value(s.cond, r)
        cond isa Bool || _cell_fail("a `while` condition is one true or false")
        cond || return nothing
        flow = _cell_exec!(s.body, r)
        flow === :break && return nothing
        flow === :return && return flow
    end
end

function _cell_exec!(s::CellIf, r::CellRun)
    for (cond, body) in s.branches
        value = _cell_value(cond, r)
        value isa Bool || _cell_fail("an `if` condition is one true or false")
        value && return _cell_exec!(body, r)
    end
    return nothing
end

function _cell_exec!(s::CellFigure, r::CellRun)
    s.kind === :table && return _cell_table!(r, s)
    s.kind === :image && return _cell_image!(r, s)
    return _cell_plot!(r, s)
end

function _cell_exec!(s::CellText, r::CellRun)
    pieces = String[p isa String ? p : _cell_show(_cell_value(p, r)) for p in s.parts]
    length(r.output) < CELL_MAX_LINES && push!(r.output, join(pieces, " "))
    return nothing
end

function _cell_exec!(s::CellDef, r::CellRun)
    r.functions[s.name] = s
    return nothing
end

function _cell_exec!(s::CellReturn, r::CellRun)
    r.depth == 0 && _cell_fail("`return` belongs in a function")
    r.returned = s.value === nothing ? nothing : _cell_value(s.value, r)
    return :return
end

_cell_exec!(s::CellJump, ::CellRun) = s.kind

function _cell_compiled(model, project_dir)
    md = IR.parse_model(model)
    flat = Compile.flatten(md; project_dir = project_dir)
    errors = [d for d in flat.diagnostics if d.severity == "error"]
    isempty(errors) && return (
        Dict{String,Any}(p.id => p.value for p in flat.parameters),
        Compile.evaluate_globals(md)[1].values,
    )
    _cell_fail("the model does not compile: " * errors[1].message)
end

"""
    cell_run(code; time, signals, model, project_dir) -> NamedTuple

Run a cell: `time` and `signals` (id => vector) are the run's data, `model` the model document
that `s"Block/param"` and global names read from. Returns `(; ok, output, figures, values,
diagnostics)`: what ran before an error is kept, and the error is an E001 to E004 diagnostic."""
function cell_run(
    code::AbstractString;
    time = nothing,
    signals = Dict{String,Vector{Float64}}(),
    model = nothing,
    project_dir = nothing,
    time_limit_s = CELL_TIME_LIMIT_S,
)
    statements, diags = parse_cell(code)
    statements === nothing && return (
        ok = false, output = String[], figures = Any[], values = Dict{String,Any}(),
        diagnostics = _diag_tuples(diags),
    )
    compiled = Ref{Any}(nothing)
    model_data = function ()
        compiled[] === nothing && (compiled[] = _cell_compiled(model, project_dir))
        return compiled[]
    end
    signal = function (id::String)
        haskey(signals, id) && return signals[id]
        value = model === nothing ? nothing : get(model_data()[1], id, nothing)
        value isa Real && return value
        _cell_fail("s\"$id\" is neither a signal of this run nor a numeric parameter of the model")
    end
    bare(name::Symbol) = model === nothing ? nothing : get(model_data()[2], name, nothing)
    env = Dict{Symbol,Any}()
    time === nothing || (env[:t] = time)
    deadline = time_ns() + round(UInt64, time_limit_s * 1e9)
    r = CellRun(
        env, env, Dict{Symbol,CellDef}(), signal, bare, String[], Any[], CELL_WORK_LIMIT, deadline,
        0, nothing,
    )
    known = Set(keys(env))
    problems = Diagnostic[]
    for s in statements
        try
            _cell_exec!(s, r)
        catch err
            (err isa ConstFoldError || err isa DomainError || err isa BoundsError ||
             err isa DivideError || err isa DimensionMismatch || err isa InexactError ||
             err isa MethodError || err isa ArgumentError || err isa StackOverflowError) || rethrow()
            message = err isa ConstFoldError ? err.message : first(split(sprint(showerror, err), '\n'))
            push!(problems, _watch_diag(
                "E004", "the cell failed: $message", s.range;
                hint = "this statement and the ones after it did not run",
            ))
            break
        end
    end
    values = Dict{String,Any}(
        String(k) => _cell_json(v) for (k, v) in r.env if !(k in known) && v isa Real
    )
    return (
        ok = isempty(problems), output = r.output, figures = r.figures, values = values,
        diagnostics = _diag_tuples(problems),
    )
end

export cell_run, parse_cell
