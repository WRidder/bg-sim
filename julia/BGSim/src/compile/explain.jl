# `model.explain` (plan 5.13; work package J4.3): what became of one signal after
# `mtkcompile`.
#
# It needs no run. The flat model gives the signal's unit and the source equations that mention
# it (with their `FlatEq.origin`); the compiled system of the compile cache (`lower_model`, J2.8)
# gives its kind: a differential state, an algebraic unknown, an observed variable (with its
# defining expression from `observed(sys)`, rendered with **our** signal ids through the
# reverse of the `Dict{String,Num}` maps of the lowering, never by parsing MTK names), an alias
# (an observed equation whose right-hand side is a single variable), a parameter, or a held
# `@discrete` output (D4). W201 and W202 findings that involve the signal are attached.
#
# This file is included by `BGSim.jl` after the lowering because it calls `lower_model`; it
# lives under `compile/` with the other model-level passes.

# ---------------------------------------------------------------------------------------
# Rendering a symbolic expression with signal ids
# ---------------------------------------------------------------------------------------

const _EXPLAIN_INFIX = Dict{Any,String}(
    (+) => "+", (-) => "-", (*) => "*", (/) => "/", (^) => "^", (<) => "<", (>) => ">",
    (<=) => "<=", (>=) => ">=", (==) => "==", (!=) => "!=", (&) => "&&", (|) => "||",
)

function _explain_variable_id(x, known::Function)
    ModelingToolkit.isvariable(x) || return nothing
    id = signal_name(Symbolics.wrap(x))
    return known(id) ? id : nothing
end

function _explain_number(x::Real)
    x isa Integer && return string(x)
    isinteger(x) && abs(x) < 1.0e15 && return string(Float64(x))
    return string(x)
end

# Parenthesise anything that is itself an infix expression.
function _explain_arg(x, known)
    text = _explain_render(x, known)
    inner = Symbolics.unwrap(x)
    if inner isa Number || _explain_variable_id(inner, known) !== nothing
        return text
    end
    Symbolics.iscall(inner) || return text
    op = Symbolics.operation(inner)
    n = length(Symbolics.arguments(inner))
    (haskey(_EXPLAIN_INFIX, op) && (n >= 2 || op === (-))) && return "(" * text * ")"
    return text
end

function _explain_render(x, known::Function)::String
    x = Symbolics.unwrap(x)
    x isa Number && return _explain_number(x)
    id = _explain_variable_id(x, known)
    id === nothing || return "s\"" * id * "\""
    if !Symbolics.iscall(x)
        return string(x)
    end
    op = Symbolics.operation(x)
    args = Symbolics.arguments(x)
    if op === ifelse && length(args) == 3
        return "ifelse(" * join((_explain_render(a, known) for a in args), ", ") * ")"
    elseif op === (-) && length(args) == 1
        return "-" * _explain_arg(args[1], known)
    elseif haskey(_EXPLAIN_INFIX, op) && length(args) >= 2
        sep = " " * _EXPLAIN_INFIX[op] * " "
        return join((_explain_arg(a, known) for a in args), sep)
    end
    name = op isa Function ? string(nameof(op)) : string(op)
    return name * "(" * join((_explain_render(a, known) for a in args), ", ") * ")"
end

# ---------------------------------------------------------------------------------------
# The source equations that mention a signal
# ---------------------------------------------------------------------------------------

_ast_mentions!(out::Set{String}, e::Name) = push!(out, String(e.name))
_ast_mentions!(out::Set{String}, e::Field) = push!(out, Flat.flat_id(e))
_ast_mentions!(::Set{String}, ::Lit) = nothing
_ast_mentions!(out::Set{String}, e::BinOp) = (_ast_mentions!(out, e.lhs); _ast_mentions!(out, e.rhs))
_ast_mentions!(out::Set{String}, e::UnOp) = _ast_mentions!(out, e.operand)
_ast_mentions!(out::Set{String}, e::Comparison) = (_ast_mentions!(out, e.lhs); _ast_mentions!(out, e.rhs))
_ast_mentions!(out::Set{String}, e::Call) = foreach(a -> _ast_mentions!(out, a), e.args)
_ast_mentions!(out::Set{String}, e::BoolOp) = foreach(a -> _ast_mentions!(out, a), e.operands)
function _ast_mentions!(out::Set{String}, e::IfElse)
    _ast_mentions!(out, e.cond)
    _ast_mentions!(out, e.then)
    _ast_mentions!(out, e.otherwise)
end
function _ast_mentions!(out::Set{String}, e::Index)
    id = _literal_index_id(e)
    id === nothing || push!(out, id)
    _ast_mentions!(out, e.base)
    foreach(i -> _ast_mentions!(out, i), e.indices)
end
_ast_mentions!(out::Set{String}, e::VectorLit) = foreach(a -> _ast_mentions!(out, a), e.elements)
_ast_mentions!(out::Set{String}, e::MatrixLit) = foreach(r -> foreach(a -> _ast_mentions!(out, a), r), e.rows)
_ast_mentions!(::Set{String}, ::Any) = nothing

# The AST as text with signals written `s"id"`, like a watch.
_ast_text(e::Name) = "s\"" * String(e.name) * "\""
_ast_text(e::Field) = "s\"" * Flat.flat_id(e) * "\""
_ast_text(e::Lit) = sprint(show, e)
_ast_text(e::BinOp) = "(" * _ast_text(e.lhs) * " " * String(e.op) * " " * _ast_text(e.rhs) * ")"
_ast_text(e::UnOp) = "(" * String(e.op) * _ast_text(e.operand) * ")"
_ast_text(e::Comparison) = "(" * _ast_text(e.lhs) * " " * String(e.op) * " " * _ast_text(e.rhs) * ")"
_ast_text(e::Call) = String(e.fn.name) * "(" * join((_ast_text(a) for a in e.args), ", ") * ")"
_ast_text(e::BoolOp) = "(" * join((_ast_text(a) for a in e.operands), " " * String(e.op) * " ") * ")"
_ast_text(e::IfElse) = "ifelse(" * _ast_text(e.cond) * ", " * _ast_text(e.then) * ", " *
                       _ast_text(e.otherwise) * ")"
_ast_text(e::Index) = _ast_text(e.base) * "[" * join((_ast_text(i) for i in e.indices), ", ") * "]"
_ast_text(e::VectorLit) = "[" * join((_ast_text(a) for a in e.elements), ", ") * "]"
_ast_text(e::Expr) = sprint(show, e)

function _explain_origin(origin::Flat.Origin)
    r = origin.range
    return (
        path = origin.path,
        ref = origin.block,
        range = r === nothing ? nothing :
                (line = r.line, col = r.col, endLine = r.endLine, endCol = r.endCol),
    )
end

function _explain_equations(flat::Flat.FlatModel, id::String)
    out = NamedTuple[]
    for eq in flat.equations
        mentioned = Set{String}()
        _ast_mentions!(mentioned, eq.lhs)
        _ast_mentions!(mentioned, eq.rhs)
        id in mentioned || continue
        push!(out, (
            text = _ast_text(eq.lhs) * " ~ " * _ast_text(eq.rhs),
            origin = _explain_origin(eq.origin),
        ))
    end
    return out
end

# ---------------------------------------------------------------------------------------
# W201 / W202
# ---------------------------------------------------------------------------------------

function _explain_involves(d::Diagnostic, id::String)
    d.code in ("W201", "W202") || return false
    occursin("`" * id * "`", d.message) && return true
    paths = d.path === nothing ? String[] : String[d.path]
    # W202 names every free instance of the loop: "algebraic loop through R1, R2".
    if d.code == "W202" && occursin("through ", d.message)
        append!(paths, strip.(split(last(split(d.message, "through "; limit = 2)), ",")))
    end
    return any(p -> id == p || startswith(id, p * "/"), paths)
end

function _explain_findings(flat::Flat.FlatModel, system, id::String)
    all = vcat(
        collect(Diagnostic, flat.diagnostics),
        Compile.post_compile_warnings(flat, system),
    )
    out = Diagnostic[]
    seen = Set{Tuple{String,String,Union{Nothing,String}}}()
    for d in all
        _explain_involves(d, id) || continue
        key = (d.code, d.message, d.path)
        key in seen && continue
        push!(seen, key)
        push!(out, d)
    end
    return Any[to_namedtuple(d) for d in sort_diagnostics(out)]
end

# ---------------------------------------------------------------------------------------
# The explanation
# ---------------------------------------------------------------------------------------

function _explain_unit(flat::Flat.FlatModel, id::String)
    for sig in flat.signals
        String(sig.id) == id && return sig.unit === nothing ? nothing : String(sig.unit)
    end
    for p in flat.parameters
        p.id == id && return p.unit === nothing ? nothing : Units.unit_string(p.unit)
    end
    return nothing
end

function _explain_failure(signal::AbstractString, diagnostics)
    return (
        signal = String(signal), kind = "observed", unit = nothing, expression = nothing,
        aliasOf = nothing, equations = NamedTuple[],
        diagnostics = Any[d isa Diagnostic ? to_namedtuple(d) : d for d in diagnostics],
    )
end

"""
    explain_signal(flat, compiled, signal) -> NamedTuple

The `explainResult` of one signal id (see the file header): `(; signal, kind, unit, expression,
aliasOf, equations, diagnostics)`. `compiled` is the [`CompiledModel`](@ref) of `flat`. An
unknown signal id gives an E003 diagnostic in the result instead of throwing."""
function explain_signal(flat::Flat.FlatModel, compiled::CompiledModel, signal::AbstractString)
    id = String(signal)
    sys = compiled.system
    known = name -> haskey(compiled.vars, name) || haskey(compiled.params, name)
    if !known(id)
        near = String[]
        for other in keys(compiled.vars)
            (endswith(other, "/" * id) || occursin(id, other)) && length(near) < 3 &&
                push!(near, other)
        end
        hint = isempty(near) ? "list the signals with model.check" :
               "did you mean " * join(("`$n`" for n in sort!(near)), ", ") * "?"
        return _explain_failure(id, [diag(
            "E003", "unknown signal `$id`"; hint = hint, scope = "explain",
        )])
    end
    unit = _explain_unit(flat, id)
    equations = _explain_equations(flat, id)
    findings = _explain_findings(flat, sys, id)
    if haskey(compiled.params, id)
        held = any(sig -> String(sig.id) == id && String(sig.kind) == "discrete", flat.signals)
        return (
            signal = id, kind = held ? "discrete" : "parameter", unit = unit,
            expression = nothing, aliasOf = nothing, equations = equations,
            diagnostics = findings,
        )
    end
    var = Symbolics.unwrap(compiled.vars[id])
    if any(u -> isequal(Symbolics.unwrap(u), var), ModelingToolkit.unknowns(sys))
        differentiated = Set{String}()
        for eq in ModelingToolkit.equations(sys)
            Compile._collect_differentials!(differentiated, eq.lhs)
            Compile._collect_differentials!(differentiated, eq.rhs)
        end
        return (
            signal = id, kind = id in differentiated ? "state" : "algebraic", unit = unit,
            expression = nothing, aliasOf = nothing, equations = equations,
            diagnostics = findings,
        )
    end
    for eq in ModelingToolkit.observed(sys)
        isequal(Symbolics.unwrap(eq.lhs), var) || continue
        rhs = Symbolics.unwrap(eq.rhs)
        alias = _explain_variable_id(rhs, known)
        return (
            signal = id, kind = alias === nothing ? "observed" : "alias", unit = unit,
            expression = alias === nothing ? _explain_render(rhs, known) : nothing,
            aliasOf = alias, equations = equations, diagnostics = findings,
        )
    end
    # Eliminated without a surviving definition (for example an unused port field).
    return (
        signal = id, kind = "observed", unit = unit, expression = nothing, aliasOf = nothing,
        equations = equations, diagnostics = findings,
    )
end

"""
    model_explain(model, project_dir, signal) -> NamedTuple

`model.explain`: parse and flatten `model` (a path, JSON text or a `Dict`), take its compiled
system from the compile cache (a cache hit costs no `mtkcompile`) and explain `signal`. A
model that does not flatten or compile gives its error diagnostics in the result."""
function model_explain(model, project_dir, signal::AbstractString)
    md = IR.parse_model(model)
    flat = Compile.flatten(md; project_dir = project_dir)
    errors = Diagnostic[d for d in flat.diagnostics if d.severity == "error"]
    isempty(errors) || return _explain_failure(signal, Any[to_namedtuple(d) for d in errors])
    settings = RunSettings(md.settings)
    lowered = try
        lower_model(flat; t_start = settings.t_start, t_end = settings.t_end)
    catch err
        return _explain_failure(signal, [_compile_diagnostic(err, flat)])
    end
    return explain_signal(flat, lowered.model, signal)
end

export explain_signal, model_explain
