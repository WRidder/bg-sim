# The `watch` expression scope (plan 5.13, decisions D22 and D27; work package J4.3).
#
# A watch is a read-only expression over a running model: literals, the whitelisted scalar
# functions, `t`, parameters, comparisons and `&& || !`, and signals. A signal is written as the
# non-standard string literal `s"Motor1/i"` (JuliaSyntax parses it as a macro call whose body
# is never evaluated); a bare name resolves relative to the optional `context` instance
# (`context = "Motor1"`, name `i` -> `Motor1/i`) and then as a model-level id. At a statement
# pause the names of the paused frame are visible as well (`debug.evaluate`, D27).
#
#   parse_watch(text)                        text -> AST (`SignalRef` for `s"..."`)
#   check_watch(expr, scope)                 names, types and units -> the resolved AST
#   watch_condition(expr)                    the real expression whose upward zero crossing is
#                                            the watch event (D19 normalization)
#
# Errors are the language's E001 to E006 diagnostics with `scope = "watch"`. User text never
# reaches `eval`: the walker below only builds our own AST nodes.

"""
    SignalRef(id, range)

A reference to a signal by its id, written `s"Motor1/i"` in a watch. `check_watch` also turns a
resolved bare name into a `SignalRef`. The constant-folding interpreter evaluates it through a
[`WatchEnv`](@ref) (see `src/sim/watch.jl`); the lowering treats it like the flat `Name`."""
struct SignalRef <: Expr
    id::String
    range::SourceRange
end

Base.show(io::IO, e::SignalRef) = print(io, "s\"", e.id, "\"")

"""
    WatchScope(signals; types = Dict(), context = nothing, locals = Symbol[])

What a watch may refer to. `signals` maps every readable id (variables, ports, parameters,
held outputs) to its dimension (`Units.Dims`, `nothing` for a wildcard); `types` maps an id to
`:Real`, `:Int` or `:Bool`; `context` is the instance path that bare names resolve in; `locals`
are the names of a paused statement frame."""
struct WatchScope
    signals::Dict{String,Any}
    types::Dict{String,Symbol}
    context::Union{Nothing,String}
    locals::Set{Symbol}
end

function WatchScope(signals::AbstractDict; types = Dict{String,Symbol}(), context = nothing,
    locals = Symbol[])
    ctx = context === nothing || isempty(strip(String(context))) ? nothing :
          String(strip(String(context)))
    return WatchScope(
        Dict{String,Any}(String(k) => v for (k, v) in signals),
        Dict{String,Symbol}(String(k) => Symbol(v) for (k, v) in types),
        ctx,
        Set{Symbol}(Symbol(l) for l in locals),
    )
end

# ---------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------

mutable struct _WatchBuilder
    diagnostics::Vector{Diagnostic}
    filename::String
end

function _watch_diag(code::AbstractString, message::AbstractString, range;
    hint = nothing)
    return diag(
        code, message; hint = hint, scope = "watch",
        source = range === nothing ? nothing : SourceRef("inline", "watch", range),
    )
end

function _werr!(b::_WatchBuilder, code, message, range; hint = nothing)
    push!(b.diagnostics, _watch_diag(code, message, range; hint = hint))
    return nothing
end

"""
    parse_watch(text) -> (expr::Union{Nothing,BGSim.Expr}, diagnostics)

Parse a watch expression. A syntax error or a construct outside the watch scope gives an
E001 diagnostic with `scope = "watch"` and a `nothing` expression."""
function parse_watch(text::AbstractString)
    src = String(text)
    b = _WatchBuilder(Diagnostic[], "watch")
    whole = SourceRange("watch", 1, 1, 1, max(1, length(src) + 1))
    if isempty(strip(src))
        _werr!(b, "E001", "the watch expression is empty", whole;
            hint = "write a condition such as s\"Motor1/i\" > 5")
        return nothing, b.diagnostics
    end
    tree = try
        JuliaSyntax.parseall(
            SyntaxNode, src; filename = "watch", ignore_errors = false, ignore_warnings = true
        )
    catch err
        err isa JuliaSyntax.ParseError || rethrow()
        for d in err.diagnostics
            d.level === :error || continue
            r = _range(err.source, d.first_byte, d.last_byte, "watch")
            _werr!(b, "E001", "syntax error: " * lowercasefirst(d.message), r)
        end
        isempty(b.diagnostics) && _werr!(b, "E001", "syntax error: the expression could not be parsed", whole)
        return nothing, b.diagnostics
    end
    items = _children(tree)
    if length(items) != 1
        _werr!(b, "E001", "a watch is exactly one expression", whole;
            hint = "combine conditions with `&&` or `||`")
        return nothing, b.diagnostics
    end
    e = _watch_to_expr!(b, items[1])
    e === nothing && isempty(b.diagnostics) &&
        _werr!(b, "E001", "the watch expression is not allowed", whole)
    return (isempty(b.diagnostics) ? e : nothing), b.diagnostics
end

function _watch_signal_id(b::_WatchBuilder, node)
    ch = _children(node)
    length(ch) == 2 && kind(ch[1]) == K"StringMacroName" && ch[1].val === Symbol("@s_str") ||
        return nothing
    body = _children(ch[2])
    if length(body) == 1 && kind(body[1]) == K"String"
        return String(body[1].val)
    elseif isempty(body)
        return ""
    end
    _werr!(b, "E001", "a signal name `s\"...\"` is plain text", _range(node, b.filename))
    return nothing
end

function _watch_to_expr!(b::_WatchBuilder, node)
    k = kind(node)
    rng = _range(node, b.filename)
    if k == K"Identifier"
        return Name(node.val, rng)
    elseif k == K"Integer" || k == K"HexInt" || k == K"OctInt" || k == K"BinInt" ||
           k == K"Float" || k == K"Bool"
        return Lit(node.val, rng)
    elseif k == K"macrocall"
        ch = _children(node)
        if !isempty(ch) && kind(ch[1]) == K"StringMacroName" && ch[1].val === Symbol("@s_str")
            id = _watch_signal_id(b, node)
            return id === nothing ? nothing : SignalRef(id, rng)
        end
        _werr!(b, "E001", "only the signal literal `s\"...\"` may be written like a macro", rng)
        return nothing
    elseif k == K"call"
        return _watch_call!(b, node)
    elseif k == K"&&" || k == K"||"
        op = k == K"&&" ? Symbol("&&") : Symbol("||")
        ops = Expr[]
        for el in _children(node)
            e = _watch_to_expr!(b, el)
            e === nothing && return nothing
            push!(ops, e)
        end
        return BoolOp(op, ops, rng)
    elseif k == K"."
        ch = _children(node)
        if length(ch) == 2 && kind(ch[1]) == K"Identifier" && kind(ch[2]) == K"Identifier"
            return Name(Symbol(String(ch[1].val) * "." * String(ch[2].val)), rng)
        end
        _werr!(b, "E001", "a port field is written `port.e` or `s\"Instance/port.e\"`", rng)
        return nothing
    elseif k == K"comparison"
        _werr!(b, "E001", "chained comparisons are not allowed", rng;
            hint = "combine two comparisons with `&&`")
        return nothing
    elseif k == K"ref" || k == K"vect" || k == K"vcat" || k == K"hcat"
        _werr!(b, "E001", "arrays and indexing are not allowed in a watch", rng;
            hint = "every signal is a scalar; write `s\"Instance/x[1]\"`")
        return nothing
    elseif k == K"string" || k == K"String"
        _werr!(b, "E001", "strings are not allowed in a watch", rng;
            hint = "write a signal as s\"Motor1/i\"")
        return nothing
    end
    _werr!(b, "E001", "$(_label(node)) is not allowed in a watch expression", rng)
    return nothing
end

function _watch_call!(b::_WatchBuilder, node)
    ch = _children(node)
    rng = _range(node, b.filename)
    isempty(ch) && return nothing
    if length(ch) == 2 && _is_operator_node(ch[1])
        op = _operator_symbol(ch[1])
        operand = _watch_to_expr!(b, ch[2])
        operand === nothing && return nothing
        if op === :- || op === :+ || op === Symbol("!")
            return UnOp(op, operand, rng)
        end
        _werr!(b, "E001", "unary `$op` is not allowed", rng)
        return nothing
    end
    if length(ch) >= 3 && _is_operator_node(ch[2])
        op = _operator_symbol(ch[2])
        if is_comparison_op(op)
            if length(ch) != 3
                _werr!(b, "E001", "operator `$op` takes two operands", rng)
                return nothing
            end
            lhs = _watch_to_expr!(b, ch[1])
            rhs = _watch_to_expr!(b, ch[3])
            (lhs === nothing || rhs === nothing) && return nothing
            return Comparison(op, lhs, rhs, rng)
        elseif op === :~ || op === Symbol("=>") || op === Symbol(":") || op === :in || op === :isa
            _werr!(b, "E001", "`$op` is not allowed in a watch expression", rng)
            return nothing
        end
        lhs = _watch_to_expr!(b, ch[1])
        lhs === nothing && return nothing
        if operator_rule_key(op) === nothing
            hint = op === Symbol("%") ? "use `mod(a, b)` or `rem(a, b)`" : nothing
            _werr!(b, "E002", "operator `$op` is not on the whitelist", _range(ch[2], b.filename);
                hint = hint)
            return nothing
        end
        for j in 3:length(ch)
            rhs = _watch_to_expr!(b, ch[j])
            rhs === nothing && return nothing
            lhs = BinOp(op, lhs, rhs, rng)
        end
        return lhs
    end
    fname = _leaf_symbol(ch[1])
    if fname === nothing
        _werr!(b, "E001", "a call must start with a function name", rng)
        return nothing
    end
    args = Expr[]
    for a in ch[2:end]
        e = _watch_to_expr!(b, a)
        e === nothing && return nothing
        push!(args, e)
    end
    if fname === :ifelse
        if length(args) == 3
            return IfElse(args[1], args[2], args[3], rng)
        end
        _werr!(b, "E001", "`ifelse` takes 3 arguments, got $(length(args))", rng;
            hint = "write `ifelse(cond, a, b)`")
        return nothing
    end
    return Call(Name(fname, _range(ch[1], b.filename)), args, rng)
end

# ---------------------------------------------------------------------------------------
# Checking: names, types, units
# ---------------------------------------------------------------------------------------

# Functions a watch may call: the scalar math of the language whitelist.
const WATCH_LOWERINGS = (:math, :nonsmooth, :discontinuous, :library)

function _watch_function_ok(fn::Symbol)
    rule = function_rule(fn)
    rule === nothing && return :unknown
    (rule.stdlib_only || !(:default in rule.contexts) || !(rule.lowering in WATCH_LOWERINGS)) &&
        return :forbidden
    return :ok
end

_unit_text(d) = d === nothing ? "unitless" : "[" * Units.unit_string(d) * "]"

_is_literal(e::Lit) = true
_is_literal(e::UnOp) = e.op in (:-, :+) && _is_literal(e.operand)
_is_literal(::Expr) = false

# Candidate ids of a bare name: relative to the context first, then model-level.
function _watch_candidates(scope::WatchScope, name::String)
    scope.context === nothing && return String[name]
    return String[scope.context * "/" * name, name]
end

struct _Checked
    expr::Union{Nothing,Expr}
    ty::Symbol            # :real, :bool or :any
    dims::Any             # Units.Dims or nothing (wildcard)
end

_signal_type(scope::WatchScope, id::String) =
    get(scope.types, id, :Real) === :Bool ? :bool : :real

function _unknown_signal(diags, id::String, range, scope::WatchScope; bare::Bool = false)
    message = bare ? "unknown name `$id` in the watch" : "unknown signal `$id`"
    near = String[]
    for known in keys(scope.signals)
        (endswith(known, "/" * id) || endswith(id, "/" * known) || occursin(id, known)) &&
            length(near) < 3 && push!(near, known)
    end
    hint = if !isempty(near)
        "did you mean " * join(("s\"$n\"" for n in sort!(near)), ", ") * "?"
    elseif scope.context !== nothing
        "write the signal as s\"Instance/name\", or check the context `$(scope.context)`"
    else
        "write a signal as s\"Instance/name\""
    end
    push!(diags, _watch_diag("E003", message, range; hint = hint))
    return nothing
end

function _check_name(e::Name, scope::WatchScope, diags)
    if e.name in scope.locals
        return _Checked(e, :any, nothing)
    elseif e.name === :t
        return _Checked(e, :real, Units.UNIT_S)
    end
    for id in _watch_candidates(scope, String(e.name))
        if haskey(scope.signals, id)
            return _Checked(SignalRef(id, e.range), _signal_type(scope, id), scope.signals[id])
        end
    end
    _unknown_signal(diags, String(e.name), e.range, scope; bare = true)
    return _Checked(nothing, :any, nothing)
end

function _check_dims_equal!(diags, what::AbstractString, lhs::_Checked, rhs::_Checked,
    le::Expr, re::Expr, range)
    (lhs.dims === nothing || rhs.dims === nothing) && return nothing
    (_is_literal(le) || _is_literal(re)) && return nothing
    Units.is_dimensionless(lhs.dims) && Units.is_dimensionless(rhs.dims) && return nothing
    lhs.dims == rhs.dims && return nothing
    push!(diags, _watch_diag(
        "E006", "$what needs equal units, got $(_unit_text(lhs.dims)) and $(_unit_text(rhs.dims))",
        range; hint = "compare quantities of the same unit; the language does no conversion"))
    return nothing
end

function _need(diags, c::_Checked, want::Symbol, what::AbstractString, range)
    (c.ty === :any || c.ty === want) && return true
    push!(diags, _watch_diag(
        "E004", "$what must be a $(want === :bool ? "Bool" : "Real") expression", range;
        hint = want === :bool ? "compare it, for example `x > 0`" :
               "a comparison is a Bool; use its two sides"))
    return false
end

function _check(e::Expr, scope::WatchScope, diags)::_Checked
    if e isa Lit
        v = e.value
        v isa Bool && return _Checked(e, :bool, nothing)
        return _Checked(e, :real, Units.DIMENSIONLESS)
    elseif e isa SignalRef
        if haskey(scope.signals, e.id)
            return _Checked(e, _signal_type(scope, e.id), scope.signals[e.id])
        end
        _unknown_signal(diags, e.id, e.range, scope)
        return _Checked(nothing, :any, nothing)
    elseif e isa Name
        return _check_name(e, scope, diags)
    elseif e isa BinOp
        l = _check(e.lhs, scope, diags)
        r = _check(e.rhs, scope, diags)
        (l.expr === nothing || r.expr === nothing) && return _Checked(nothing, :real, nothing)
        ok = _need(diags, l, :real, "an operand of `$(e.op)`", e.lhs.range) &
             _need(diags, r, :real, "an operand of `$(e.op)`", e.rhs.range)
        node = BinOp(e.op, l.expr, r.expr, e.range)
        ok || return _Checked(node, :real, nothing)
        if e.op === :+ || e.op === :-
            _check_dims_equal!(diags, "`$(e.op)`", l, r, e.lhs, e.rhs, e.range)
            d = l.dims === nothing || _is_literal(e.lhs) ? r.dims : l.dims
            return _Checked(node, :real, d)
        elseif e.op === :*
            d = l.dims === nothing || r.dims === nothing ? nothing : l.dims * r.dims
            return _Checked(node, :real, d)
        elseif e.op === :/
            d = l.dims === nothing || r.dims === nothing ? nothing : l.dims / r.dims
            return _Checked(node, :real, d)
        elseif e.op === :^
            d = nothing
            if l.dims !== nothing && Units.is_dimensionless(l.dims)
                d = Units.DIMENSIONLESS
            elseif l.dims !== nothing && e.rhs isa Lit && e.rhs.value isa Integer
                d = l.dims^Int(e.rhs.value)
            end
            return _Checked(node, :real, d)
        end
        return _Checked(node, :real, nothing)
    elseif e isa UnOp
        c = _check(e.operand, scope, diags)
        c.expr === nothing && return _Checked(nothing, e.op === Symbol("!") ? :bool : :real, nothing)
        if e.op === Symbol("!")
            _need(diags, c, :bool, "the operand of `!`", e.operand.range)
            return _Checked(UnOp(e.op, c.expr, e.range), :bool, nothing)
        end
        _need(diags, c, :real, "the operand of `$(e.op)`", e.operand.range)
        return _Checked(UnOp(e.op, c.expr, e.range), :real, c.dims)
    elseif e isa Comparison
        l = _check(e.lhs, scope, diags)
        r = _check(e.rhs, scope, diags)
        (l.expr === nothing || r.expr === nothing) && return _Checked(nothing, :bool, nothing)
        _need(diags, l, :real, "a compared value", e.lhs.range)
        _need(diags, r, :real, "a compared value", e.rhs.range)
        _check_dims_equal!(diags, "a comparison", l, r, e.lhs, e.rhs, e.range)
        return _Checked(Comparison(e.op, l.expr, r.expr, e.range), :bool, nothing)
    elseif e isa BoolOp
        ops = Expr[]
        ok = true
        for o in e.operands
            c = _check(o, scope, diags)
            c.expr === nothing && (ok = false; continue)
            _need(diags, c, :bool, "an operand of `$(e.op)`", o.range)
            push!(ops, c.expr)
        end
        ok || return _Checked(nothing, :bool, nothing)
        return _Checked(BoolOp(e.op, ops, e.range), :bool, nothing)
    elseif e isa IfElse
        c = _check(e.cond, scope, diags)
        a = _check(e.then, scope, diags)
        o = _check(e.otherwise, scope, diags)
        (c.expr === nothing || a.expr === nothing || o.expr === nothing) &&
            return _Checked(nothing, :real, nothing)
        _need(diags, c, :bool, "the condition of `ifelse`", e.cond.range)
        _check_dims_equal!(diags, "the two branches of `ifelse`", a, o, e.then, e.otherwise, e.range)
        ty = a.ty === :any ? o.ty : a.ty
        return _Checked(IfElse(c.expr, a.expr, o.expr, e.range), ty, a.dims === nothing ? o.dims : a.dims)
    elseif e isa Call
        status = _watch_function_ok(e.fn.name)
        if status === :unknown
            push!(diags, _watch_diag("E002", "function `$(e.fn.name)` is not on the whitelist", e.fn.range;
                hint = "see the built-in function table in the language spec"))
            return _Checked(nothing, :real, nothing)
        elseif status === :forbidden
            push!(diags, _watch_diag("E002", "`$(e.fn.name)` cannot be used in a watch", e.fn.range;
                hint = "a watch reads values; use the scalar math functions"))
            return _Checked(nothing, :real, nothing)
        end
        rule = function_rule(e.fn.name)
        n = length(e.args)
        if n < rule.min_args || (rule.max_args >= 0 && n > rule.max_args)
            push!(diags, _watch_diag("E004",
                "`$(e.fn.name)` takes $(rule.min_args == rule.max_args ? string(rule.min_args) : "$(rule.min_args) to $(rule.max_args < 0 ? "any number of" : rule.max_args)") argument(s), got $n",
                e.range))
            return _Checked(nothing, :real, nothing)
        end
        checked = _Checked[_check(a, scope, diags) for a in e.args]
        any(c -> c.expr === nothing, checked) && return _Checked(nothing, :real, nothing)
        for (c, a) in zip(checked, e.args)
            _need(diags, c, :real, "an argument of `$(e.fn.name)`", a.range)
        end
        node = Call(e.fn, Expr[c.expr for c in checked], e.range)
        fn = e.fn.name
        if fn in (:abs, :min, :max, :clamp, :hypot, :floor, :ceil, :round, :deadzone, :saturate)
            for j in 2:length(checked)
                fn in (:deadzone, :saturate, :clamp) && break
                _check_dims_equal!(diags, "`$fn`", checked[1], checked[j], e.args[1], e.args[j], e.range)
            end
            return _Checked(node, :real, checked[1].dims)
        end
        return _Checked(node, :real, Units.DIMENSIONLESS)
    end
    push!(diags, _watch_diag("E001", "this expression is not allowed in a watch", expr_range(e)))
    return _Checked(nothing, :real, nothing)
end

"""
    check_watch(expr, scope) -> (resolved, type, dims, diagnostics)

Resolve the names of a parsed watch against `scope` and check its types and units. `resolved`
has every signal as a [`SignalRef`](@ref) (`nothing` on an error); `type` is `:real`, `:bool`
or `:any`; `dims` is the unit of the result (`Units.Dims`, or `nothing` when unknown).
Unknown names are E003, type errors E004, non-whitelisted functions E002 and unit mismatches
E006, all with `scope = "watch"`."""
function check_watch(expr::Expr, scope::WatchScope)
    diags = Diagnostic[]
    c = _check(expr, scope, diags)
    has_error = any(d -> d.severity == "error", diags)
    return (has_error ? nothing : c.expr), c.ty, c.dims, diags
end

# ---------------------------------------------------------------------------------------
# The condition (D19)
# ---------------------------------------------------------------------------------------

"""
    watch_condition(resolved) -> (cond::Union{Nothing,Expr}, diagnostics)

The real expression whose **upward zero crossing** is the watch event, normalized like an
`@events` condition (D19): `a > b` and `a >= b` become `a - b`, `a < b` and `a <= b` become
`b - a`, `a == b` becomes `a - b`, `c1 && c2` the minimum, `c1 || c2` the maximum and `!c` the
negation of the operands' conditions. A bare real expression fires when it crosses zero
upward. `!=` and a bare Bool have no crossing and are E004."""
function watch_condition(e::Expr)
    diags = Diagnostic[]
    c = _condition(e, diags)
    return (isempty(diags) ? c : nothing), diags
end

function _condition(e::Comparison, diags)
    r = e.range
    if e.op === :< || e.op === :<=
        return BinOp(:-, e.rhs, e.lhs, r)
    elseif e.op === :> || e.op === :>= || e.op === Symbol("==")
        return BinOp(:-, e.lhs, e.rhs, r)
    end
    push!(diags, _watch_diag("E004", "`!=` has no crossing, so it cannot be a watch", r;
        hint = "use `>` or `<`, or combine them with `||`"))
    return nothing
end

function _condition(e::BoolOp, diags)
    parts = Expr[]
    for o in e.operands
        c = _condition(o, diags)
        c === nothing || push!(parts, c)
    end
    (isempty(parts) || length(parts) != length(e.operands)) && return nothing
    e.op === Symbol("&&") && return Call(Name(:min, e.range), parts, e.range)
    e.op === Symbol("||") && return Call(Name(:max, e.range), parts, e.range)
    length(parts) == 1 && return UnOp(:-, parts[1], e.range)
    return nothing
end

function _condition(e::UnOp, diags)
    if e.op === Symbol("!")
        c = _condition(e.operand, diags)
        return c === nothing ? nothing : UnOp(:-, c, e.range)
    end
    return e
end

function _condition(e::Lit, diags)
    e.value isa Bool && return Lit(e.value ? 1.0 : -1.0, e.range)
    return e
end

function _condition(e::Expr, diags)
    return e
end

# A copy of `e` where every `SignalRef` is the flat `Name` the lowering understands.
flat_names(e::SignalRef) = Name(Symbol(e.id), e.range)
flat_names(e::Name) = e
flat_names(e::Lit) = e
flat_names(e::BinOp) = BinOp(e.op, flat_names(e.lhs), flat_names(e.rhs), e.range)
flat_names(e::UnOp) = UnOp(e.op, flat_names(e.operand), e.range)
flat_names(e::Call) = Call(e.fn, Expr[flat_names(a) for a in e.args], e.range)
flat_names(e::IfElse) = IfElse(flat_names(e.cond), flat_names(e.then), flat_names(e.otherwise), e.range)
flat_names(e::Comparison) = Comparison(e.op, flat_names(e.lhs), flat_names(e.rhs), e.range)
flat_names(e::BoolOp) = BoolOp(e.op, Expr[flat_names(a) for a in e.operands], e.range)

# The signal ids a resolved watch reads.
signal_refs(e::SignalRef) = String[e.id]
signal_refs(::Union{Name,Lit}) = String[]
signal_refs(e::BinOp) = vcat(signal_refs(e.lhs), signal_refs(e.rhs))
signal_refs(e::UnOp) = signal_refs(e.operand)
signal_refs(e::Call) = reduce(vcat, (signal_refs(a) for a in e.args); init = String[])
signal_refs(e::IfElse) = vcat(signal_refs(e.cond), signal_refs(e.then), signal_refs(e.otherwise))
signal_refs(e::Comparison) = vcat(signal_refs(e.lhs), signal_refs(e.rhs))
signal_refs(e::BoolOp) = reduce(vcat, (signal_refs(a) for a in e.operands); init = String[])

export SignalRef, WatchScope, parse_watch, check_watch, watch_condition
