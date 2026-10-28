# The block-level unit check (plan 5.3, decision D2): E006 for every inconsistency, including a
# scale-only difference in `+ - ~` and comparisons.
#
# `check_units(pb)` is called from `BGSim.check_block` (plan 4.4, check 6) and is total: it
# never throws on user input and returns a (possibly empty) `Vector{Diagnostic}` whose
# sources point at the offending term in the block's own source. It runs after the name,
# type and size checks, but it assumes nothing about them: undeclared names, strings and
# unknown functions are wildcards, so a block that already has E003/E004 does not collect
# a cascade of unit errors.
#
# Rules, exactly as plan 5.3:
#   * `+ - ~` and comparisons need equal dimensions (exponents and scale). A scale-only
#     difference is E006 too: the language does no runtime conversion, so `1 mm + 1 m` would
#     silently add 1 to 1. The message names both units and the factor (orchestrator decision
#     FIX-M1-1: the earlier I101 info code was outside the diagnostic contract, whose `code`
#     pattern is `^[EW][0-9]{3}$`);
#   * `* /` add/subtract exponents and multiply/divide scales;
#   * `^` needs an integer exponent (a literal, or a `@constants` value that folds to one);
#     a dimensionless base may take any real exponent;
#   * functions need dimensionless arguments, except `abs sign min max clamp hypot`
#     (same dimension in and out), `sqrt` (halves the exponents) and the library
#     functions `deadzone`/`saturate` (in = out, like `clamp`);
#   * variables and parameters without a unit are wildcards: a wildcard term skips the
#     check. This is *not* inference. Numeric literals are wildcards in `+`/`-` (write
#     `x + 0.0` in any unit), and multiplicative identities in `*`/`/` (`2*x` is `x`);
#   * `ddt(x)` is `x/s` and `int(x, x0)` is `x*s` — that is what makes the bond-graph
#     storage elements (`q` in `flow*s`, `ddt(q) ~ p.f`) check;
#   * `t` is `s`. Port fields `p.e`/`p.f` take the effort/flow of the port's domain; a
#     multibond port exposes one unit **per component** (`p.e[1]` is a torque, `p.e[2]` a
#     force: F9/D-MB10), `p.P` is the scalar power `Σ_k e[k]*f[k]` in W, and a block with a
#     concrete port domain has its `effort`/`flow` units substituted (decision D9). A
#     `Generic` block keeps them symbolic until a connection adopts it;
#   * the connection-level E102 (different dimensions on a wire) is J2.5. The factor that
#     wire needs is `conversion_factor` in `dims.jl`, tested here.
#
# The environment is built from the declarations and ports of the block. `unit_env(pb)` is
# public so J2.5 and the editor can ask for the same map without re-deriving it.

using ..BGSim:
    ParsedBlock,
    Diagnostic,
    SourceRange,
    diag,
    source_range,
    block_source,
    block_range,
    constant_env,
    decl_name,
    decl_attrs,
    decl_type,
    decl_scope,
    declarations,
    ports,
    equations,
    initial_equations,
    discrete_scopes,
    discrete_body,
    events,
    type_domain,
    Lit,
    Name,
    Field,
    Call,
    BinOp,
    UnOp,
    Index,
    VectorLit,
    MatrixLit,
    IfElse,
    Comparison,
    BoolOp,
    Equation,
    IfEquation,
    ForEquation,
    Assign,
    IfStatement,
    ForStatement,
    CallStatement,
    EventDecl

"""The declaration scopes that may carry a `unit` attribute (plan 4.3)."""
const UNIT_SCOPES = (:constants, :parameters, :inputs, :outputs, :variables)

# ---------------------------------------------------------------------------------------
# The unit environment
# ---------------------------------------------------------------------------------------

"""    UnitEnv(names, labels, constants)

The names the unit checker resolves, built by [`unit_env`](@ref):

* `names` maps a declaration name to its [`Dims`](@ref); a name that is absent is a
  wildcard. Port fields are stored under `Symbol("p.e")` / `Symbol("p.f")` for a scalar
  port, under `Symbol("p.e[k]")` / `Symbol("p.f[k]")` for each component of a multibond
  port (D-MB10), and the derived power under `Symbol("p.P")`.
* `labels` maps the same names to the unit text the user wrote (or the domain spelling for
  a port field, e.g. `"N*m"` for `p.e[1]` and `"N"` for `p.e[2]`), so a diagnostic can say
  `[mm]` and `[N*m]` instead of a canonical expansion.
* `constants` is the folded `@constants` map: a scalar constant used as a multiplicative
  factor (`2*x`, `x^N`) keeps the other operand's unit.

`UnitEnv(Dict(:x => parse_unit("m")))` is the short form for tests and for callers that
only have a name-to-dimension map; a `nothing` value means wildcard and is skipped.
"""
struct UnitEnv
    names::Dict{Symbol,Dims}
    labels::Dict{Symbol,String}
    constants::Dict{Symbol,Any}
end

UnitEnv() = UnitEnv(Dict{Symbol,Dims}(), Dict{Symbol,String}(), Dict{Symbol,Any}())

function UnitEnv(names::AbstractDict)
    table = Dict{Symbol,Dims}()
    for (name, dims) in names
        name isa Symbol || throw(ArgumentError("unit names must be Symbols, got `$name`"))
        dims === nothing && continue
        dims isa Dims || throw(ArgumentError("the unit of `$name` must be a Dims or nothing"))
        table[name] = dims
    end
    return UnitEnv(table, Dict{Symbol,String}(), Dict{Symbol,Any}())
end

"""    block_domain(pb) -> Symbol

The concrete power domain of a block: the first non-`Generic` `@ports` domain, else
`:Generic`. The connection pass (J2.5) owns the case of a block that mixes concrete
domains (E102); the unit checker only needs one domain to adopt the `effort`/`flow`
pseudo-dimensions (decision D9)."""
function block_domain(pb::ParsedBlock)::Symbol
    for p in ports(pb)
        domain = type_domain(decl_type(p))
        (domain === nothing || domain === :Generic) && continue
        return domain
    end
    return :Generic
end

"""    unit_env(pb::ParsedBlock[, domain::Symbol]) -> UnitEnv

Build the unit environment of a block: every `unit` attribute of `@constants`,
`@parameters`, `@inputs`, `@outputs` and `@variables`, the `e`/`f` fields of every power
port, and `t` (seconds). Units that do not parse are left out of the environment (see
[`check_units`](@ref) for the E006); `effort`/`flow` are substituted when the block has a
concrete domain.

`domain` is the domain the block's ports actually adopted (plan 5.6, J2.5). It defaults to
[`block_domain`](@ref)`(pb)`. When it is concrete and the block itself is `Generic`, the
pseudo-dimensions of the declarations and of the `Generic` port fields are substituted with
that domain's units, and the declaration labels become the concrete unit text (`c` written
as `flow*s/effort` is labelled `F` on an Electrical island). This is the per-instance
environment the flattener passes to [`check_units`](@ref) after adoption."""
function unit_env(pb::ParsedBlock, domain::Symbol = block_domain(pb))::UnitEnv
    return _build_env(pb, nothing, domain)
end

function _build_env(
    pb::ParsedBlock,
    diags::Union{Vector{Diagnostic},Nothing},
    domain::Symbol = block_domain(pb),
)::UnitEnv
    names = Dict{Symbol,Dims}()
    labels = Dict{Symbol,String}()
    names[:t] = UNIT_S
    labels[:t] = "s"
    # `adopted` means a Generic block is being checked under the domain its islands gave it;
    # a block with its own concrete port domain keeps its own domain (and its written labels).
    adopted = domain !== block_domain(pb)
    for scope in UNIT_SCOPES
        for d in declarations(pb, scope)
            text = get(decl_attrs(d), :unit, nothing)
            text isa AbstractString || continue
            dims = try
                parse_unit(text)
            catch err
                err isa UnitParseError || rethrow()
                if diags !== nothing
                    push!(
                        diags,
                        diag(
                            "E006",
                            "invalid unit \"$text\": $(err.reason)",
                            pb,
                            d;
                            hint = "write a unit such as \"N*m\", \"rad/s\" or \"flow*s/effort\"",
                            scope = decl_scope(d),
                        ),
                    )
                end
                continue
            end
            name = decl_name(d)
            substituted = substitute_domain(dims, domain)
            names[name] = substituted
            # A Generic block that became concrete reports the concrete unit text, so a
            # model-level E006 names the units the user sees after adoption.
            labels[name] = (adopted && has_pseudo_dimensions(dims)) ?
                           unit_string(substituted) : String(text)
        end
    end
    for p in ports(pb)
        name = decl_name(p)
        port_domain = something(type_domain(decl_type(p)), :Generic)
        if adopted && port_domain === :Generic
            # A Generic block whose island adopted a scalar domain takes that domain's
            # units. A Generic *scalar* port cannot adopt a multibond domain (J-MB1
            # reports E102); it keeps its pseudo-dimensions here rather than inventing a
            # first component.
            component_count(domain) == 1 && (port_domain = domain)
        end
        effort_labels = domain_effort_unit_strings(port_domain)
        flow_labels = domain_flow_unit_strings(port_domain)
        for k in 1:component_count(port_domain)
            ekey = component_key(name, "e", k, component_count(port_domain))
            fkey = component_key(name, "f", k, component_count(port_domain))
            names[ekey] = effort_dims(port_domain, k)
            names[fkey] = flow_dims(port_domain, k)
            labels[ekey] = effort_labels[k]
            labels[fkey] = flow_labels[k]
        end
        names[Symbol(name, ".P")] = power_dims(port_domain)
        labels[Symbol(name, ".P")] = unit_string(power_dims(port_domain))
    end
    return UnitEnv(names, labels, constant_env(pb))
end

"""    component_key(port, field, k, n) -> Symbol

The environment key of component `k` of a power-port field: `Symbol("p.e")` for a scalar
port (`n == 1`) and `Symbol("p.e[k]")` for a multibond one. The scalar spelling is kept for
every existing one-component port, so no M2 block changes behaviour."""
function component_key(port::Symbol, field::AbstractString, k::Integer, n::Integer)
    n == 1 && return Symbol(port, '.', field)
    return Symbol(port, ".", field, "[", string(k), "]")
end

# ---------------------------------------------------------------------------------------
# Diagnostic context
# ---------------------------------------------------------------------------------------

mutable struct _Ctx
    env::UnitEnv
    pb::Union{ParsedBlock,Nothing}
    diags::Vector{Diagnostic}
    report::Bool
    scope::Symbol
    text::String
    loops::Dict{Symbol,Int}
end

_ctx(env::UnitEnv) = _Ctx(env, nothing, Diagnostic[], false, :equations, "", Dict{Symbol,Int}())

function _report!(
    ctx::_Ctx,
    code::AbstractString,
    message::AbstractString,
    node;
    hint = nothing,
)
    if ctx.report && ctx.pb !== nothing
        push!(
            ctx.diags,
            diag(code, message, ctx.pb, node; hint = hint, scope = ctx.scope),
        )
    end
    return nothing
end

"""The ` in "…"` clause of a message, when the checker is inside an equation."""
function _in_equation(ctx::_Ctx)::String
    return isempty(ctx.text) ? "" : " in \"" * ctx.text * "\""
end

"""    _source_slice(pb, range) -> String

The user's source text for a range, collapsed onto one line. `block_source(pb)` is the
block slice, not the whole file, so the block's start line/column are subtracted first."""
function _source_slice(pb::ParsedBlock, r::SourceRange)::String
    lines = split(block_source(pb), '\n')
    start = block_range(pb)
    out = String[]
    for line_no in r.line:r.endLine
        idx = line_no - start.line + 1
        (idx < 1 || idx > length(lines)) && continue
        chars = collect(lines[idx])
        first_col = line_no == start.line ? start.col : 1
        a = line_no == r.line ? max(r.col - first_col + 1, 1) : 1
        z = line_no == r.endLine ? min(r.endCol - first_col + 1, length(chars)) : length(chars)
        a <= z && push!(out, String(chars[a:z]))
    end
    return _collapse(join(out, " "))
end

_collapse(s::AbstractString) = strip(replace(String(s), r"\s+" => " "))

function _short(s::AbstractString, limit::Int = 72)::String
    chars = collect(String(s))
    length(chars) <= limit && return String(chars)
    return String(chars[1:limit]) * "…"
end

"""The source text of a term, for a hint that names the offending term."""
function _term_text(ctx::_Ctx, node)::String
    if ctx.pb !== nothing
        text = _short(_source_slice(ctx.pb, source_range(node)), 40)
        isempty(text) || return text
    end
    return _short(sprint(show, node), 40)
end

"""The unit label to use in a message: the declaration's own spelling when the node is a
declared name or port field, else the canonical [`unit_string`](@ref)."""
function _label(ctx::_Ctx, node, d::Dims)::String
    declared = _declared_label(ctx, node)
    return declared === nothing ? unit_string(d) : declared
end

_declared_label(ctx::_Ctx, node) = _declared_label(ctx.env, node)

function _declared_label(ctx::_Ctx, node::Index)
    key = _component_key(node, _index_value(ctx, node.indices[1]))
    key === nothing || return get(ctx.env.labels, key, nothing)
    return _declared_label(ctx.env, node.base)
end

_declared_label(env::UnitEnv, node::Name) = get(env.labels, node.name, nothing)
function _declared_label(env::UnitEnv, node::Field)
    key = _field_key(node)
    return key === nothing ? nothing : get(env.labels, key, nothing)
end
function _declared_label(env::UnitEnv, node::UnOp)
    return node.op === Symbol("-") || node.op === Symbol("+") ?
           _declared_label(env, node.operand) : nothing
end
_declared_label(env::UnitEnv, node::Index) = _declared_label(env, node.base)
_declared_label(::UnitEnv, ::Any) = nothing

_field_key(node::Field) =
    node.base isa Name ? Symbol(node.base.name, '.', node.field) : nothing

"""    _component_key(node::Index, k) -> Union{Symbol,Nothing}

The `p.e[k]` environment key of an indexed port field, or `nothing` when the expression is
not `port.field[component]` with a statically known component. `k` is resolved through the
enclosing `for` loop's binding by [`_index_value`](@ref), so both `p.e[1]` and the unrolled
`for k in 1:D` form see the component's own unit."""
function _component_key(node::Index, k::Union{Int,Nothing})
    node.base isa Field || return nothing
    field = node.base::Field
    field.base isa Name || return nothing
    k === nothing && return nothing
    return Symbol((field.base::Name).name, '.', field.field, '[', string(k), ']')
end

"""    _index_value(ctx, e) -> Union{Int,Nothing}

The integer value of an index expression: a folded integer (a literal, or a `for` bound the
parser already folded), a negated literal, or an enclosing `for` loop's variable. Anything
else is `nothing` (the unit lookup then falls back to the field as a whole, which for a
multibond port is a wildcard — never a single component)."""
_index_value(::_Ctx, e::Integer) = e isa Bool ? nothing : Int(e)

_index_value(::_Ctx, e::Lit) =
    e.value isa Integer && !(e.value isa Bool) ? Int(e.value) : nothing

_index_value(ctx::_Ctx, e::Name) = get(ctx.loops, e.name, nothing)

function _index_value(ctx::_Ctx, e::UnOp)
    (e.op === Symbol("-") || e.op === Symbol("+")) || return nothing
    value = _index_value(ctx, e.operand)
    value === nothing && return nothing
    return e.op === Symbol("-") ? -value : value
end

_index_value(::_Ctx, ::Any) = nothing

"""    _for_each_iteration(f, ctx, var, lo, hi, step)

Unroll a `for` loop for the unit pass: bind the loop variable to every value the body runs
with, so `p.e[k]` is checked against the unit of **each** component, not only of the first.
`lo`/`hi`/`step` are folded integers in the AST (E005 otherwise); when one is not known, the
body is checked once with no binding, which makes a component lookup a wildcard."""
function _for_each_iteration(f::Function, ctx::_Ctx, var::Symbol, lo, hi, step)
    first = _index_value(ctx, lo)
    last = _index_value(ctx, hi)
    stride = step === nothing ? 1 : _index_value(ctx, step)
    if first === nothing || last === nothing || stride === nothing || stride == 0
        return _with_loop(f, ctx, var, first)
    end
    for k in first:stride:last
        _with_loop(f, ctx, var, k)
    end
    return nothing
end

"""    _with_loop(f, ctx, var, value)

Run `f()` with the `for` loop variable `var` bound to `value` (when known), restoring the
previous binding afterwards. The unit pass unrolls the loop by binding the index here, so a
component lookup sees the unit of the component that iteration names."""
function _with_loop(f::Function, ctx::_Ctx, var::Symbol, value::Union{Int,Nothing})
    previous = get(ctx.loops, var, nothing)
    value === nothing || (ctx.loops[var] = value)
    try
        f()
    finally
        previous === nothing ? delete!(ctx.loops, var) : (ctx.loops[var] = previous)
    end
    return nothing
end

_same_scale(a::Dims, b::Dims) = isapprox(a.scale, b.scale; rtol = 1e-12)

"""    _scale_hint!(ctx, node, d, ref_node, reference) -> nothing

Report E006 for a scale-only difference and nothing else. Plan 5.3 requires equal dimensions
(exponents **and** scale) for `+ - ~` and comparisons, and the language does no runtime
conversion (spec: "no runtime conversion"), so `1 mm + 1 m` would silently add 1 to 1. This is
therefore an error, not a hint, and it uses the contract's E006 code (the diagnostic schema only
admits `E`/`W` codes)."""
function _scale_hint!(ctx::_Ctx, node, d::Dims, ref_node, reference::Dims)
    _same_scale(d, reference) && return nothing
    factor = d.scale / reference.scale
    _report!(
        ctx,
        "E006",
        "[" * _label(ctx, node, d) * "] and [" * _label(ctx, ref_node, reference) *
        "] differ only in scale: [" * _label(ctx, node, d) * "] to [" *
        _label(ctx, ref_node, reference) * "] is ×" * string(factor) *
        _in_equation(ctx),
        node;
        hint = "write both operands in the same unit; the language does not convert at run time",
    )
    return nothing
end

"""    _common!(ctx, items; what) -> Union{Dims,Nothing}

The common dimension of `items` (pairs of `(node, dims)`). A numeric literal is ignored (it
is legal in any unit); any other wildcard makes the result unknown and skips the check
(plan 5.3: no inference from a wildcard). A dimension mismatch is E006 at the offending
item and returns `nothing` (which suppresses cascades); a scale-only difference is E006 too and
keeps the first item's reference."""
function _common!(ctx::_Ctx, items::AbstractVector; what::AbstractString)
    known = Tuple{Any,Dims}[]
    for item in items
        if item[2] === nothing
            # A literal in `min(x, 0.0)` is fine; an ununit-ed name could be anything.
            _scalar_value(ctx, item[1]) === nothing && return nothing
            continue
        end
        push!(known, (item[1], item[2]::Dims))
    end
    isempty(known) && return nothing
    ref_node, ref_dims = known[1]
    for (node, dims) in known[2:end]
        if dims.exps != ref_dims.exps
            _report!(
                ctx,
                "E006",
                what * ": [" * _label(ctx, node, dims) * "] and [" *
                _label(ctx, ref_node, ref_dims) * "]" * _in_equation(ctx),
                node;
                hint = "`" * _term_text(ctx, node) * "` is [" * _label(ctx, node, dims) *
                       "] but `" * _term_text(ctx, ref_node) * "` is [" *
                       _label(ctx, ref_node, ref_dims) * "]",
            )
            return nothing
        end
        _scale_hint!(ctx, node, dims, ref_node, ref_dims)
    end
    return ref_dims
end

# ---------------------------------------------------------------------------------------
# Scalar folds (a `@constants` value or a literal number)
# ---------------------------------------------------------------------------------------

_scalar_value(ctx::_Ctx, e::Lit) =
    e.value isa Bool ? nothing : e.value isa Real ? Float64(e.value) : nothing

function _scalar_value(ctx::_Ctx, e::Name)
    # A constant with a unit is a quantity, not a scale factor.
    haskey(ctx.env.names, e.name) && return nothing
    value = get(ctx.env.constants, e.name, nothing)
    return value isa Real && !(value isa Bool) ? Float64(value) : nothing
end

function _scalar_value(ctx::_Ctx, e::UnOp)
    (e.op === Symbol("-") || e.op === Symbol("+")) || return nothing
    value = _scalar_value(ctx, e.operand)
    value === nothing && return nothing
    return e.op === Symbol("-") ? -value : value
end

_scalar_value(::_Ctx, ::Any) = nothing

# ---------------------------------------------------------------------------------------
# Expression units
# ---------------------------------------------------------------------------------------

"""    dims_of(expr, env) -> Union{Dims,Nothing}

The dimension of an expression under `env`, or `nothing` for a wildcard (a variable or
parameter without a unit, a numeric literal, an undeclared name, an unknown call). This is
the pure form of the check: it never reports, and a wildcard anywhere in a sum or product
makes the result a wildcard.

`env` is a [`UnitEnv`](@ref) or any `AbstractDict{Symbol,Dims}` (absent key = wildcard)."""
dims_of(e, env::UnitEnv) = _dims!(_ctx(env), e)
dims_of(e, env::AbstractDict) = dims_of(e, UnitEnv(env))
dims_of(e) = dims_of(e, UnitEnv())

# Unknown node kinds are wildcards: the fast check must stay total on partial ASTs.
_dims!(::_Ctx, ::Any) = nothing

_dims!(::_Ctx, ::Lit) = nothing

_dims!(ctx::_Ctx, e::Name) = get(ctx.env.names, e.name, nothing)

function _dims!(ctx::_Ctx, e::Field)
    key = _field_key(e)
    return key === nothing ? nothing : get(ctx.env.names, key, nothing)
end

function _dims!(ctx::_Ctx, e::UnOp)
    d = _dims!(ctx, e.operand)
    return e.op === Symbol("-") || e.op === Symbol("+") ? d : nothing
end

"""`v[i]` keeps the element unit of `v`. For a multibond port field `p.e[k]`/`p.f[k]` the
component's own unit is looked up first (D-MB10: a torque is not a force); a scalar port
keeps the historical whole-field lookup."""
function _dims!(ctx::_Ctx, e::Index)
    key = _component_key(e, _index_value(ctx, e.indices[1]))
    if key !== nothing
        d = get(ctx.env.names, key, nothing)
        d === nothing || return d
    end
    return _dims!(ctx, e.base)
end

function _dims!(ctx::_Ctx, e::VectorLit)
    return _common!(
        ctx,
        [(el, _dims!(ctx, el)) for el in e.elements];
        what = "the elements of a vector literal must have one unit",
    )
end

function _dims!(ctx::_Ctx, e::MatrixLit)
    items = Tuple{Any,Union{Dims,Nothing}}[]
    for row in e.rows, el in row
        push!(items, (el, _dims!(ctx, el)))
    end
    return _common!(
        ctx,
        items;
        what = "the elements of a matrix literal must have one unit",
    )
end

function _dims!(ctx::_Ctx, e::BinOp)
    op = e.op
    op === Symbol("+") && return _add!(ctx, e, Symbol("+"))
    op === Symbol("-") && return _add!(ctx, e, Symbol("-"))
    op === Symbol("*") && return _mul!(ctx, e)
    op === Symbol("/") && return _div!(ctx, e)
    op === Symbol("^") && return _pow!(ctx, e)
    op === Symbol("\\") && return _div!(ctx, e; solve = true)
    _dims!(ctx, e.lhs)
    _dims!(ctx, e.rhs)
    return nothing
end

"""`+` and `-` need equal dimensions (plan 5.3). The offending term is the right one: the
checker accumulates left to right, so the message reads "cannot add [m/s] to [N]"."""
function _add!(ctx::_Ctx, e::BinOp, op::Symbol)
    ld = _dims!(ctx, e.lhs)
    rd = _dims!(ctx, e.rhs)
    if ld === nothing || rd === nothing
        # A numeric literal is a unitless zero/scale factor and does not hide the other
        # side's unit; any other wildcard makes the sum unknown (plan 5.3: a wildcard term
        # skips the check, it is not inferred).
        if ld === nothing && _scalar_value(ctx, e.lhs) === nothing
            return nothing
        elseif rd === nothing && _scalar_value(ctx, e.rhs) === nothing
            return nothing
        end
        return ld === nothing ? rd : ld
    end
    if ld.exps == rd.exps
        _scale_hint!(ctx, e.rhs, rd, e.lhs, ld)
        return ld
    end
    verb = op === Symbol("+") ? "add" : "subtract"
    prep = op === Symbol("+") ? "to" : "from"
    _report!(
        ctx,
        "E006",
        "cannot " * verb * " [" * _label(ctx, e.rhs, rd) * "] " * prep * " [" *
        _label(ctx, e.lhs, ld) * "]" * _in_equation(ctx),
        e.rhs;
        hint = "`" * _term_text(ctx, e.rhs) * "` is [" * _label(ctx, e.rhs, rd) *
               "] but `" * _term_text(ctx, e.lhs) * "` is [" * _label(ctx, e.lhs, ld) *
               "]",
    )
    return nothing
end

"""`*` multiplies the dimensions. A numeric literal or a scalar `@constants` value is a
multiplicative identity, so `2*x` keeps `x`'s dimension."""
function _mul!(ctx::_Ctx, e::BinOp)
    ld = _dims!(ctx, e.lhs)
    rd = _dims!(ctx, e.rhs)
    if ld === nothing
        return _scalar_value(ctx, e.lhs) === nothing ? nothing : rd
    elseif rd === nothing
        return _scalar_value(ctx, e.rhs) === nothing ? nothing : ld
    end
    return ld * rd
end

"""`/` subtracts the dimensions. A numeric literal numerator is the reciprocal
(`1/x` is `1/[x]`); a numeric literal denominator is a multiplicative identity."""
function _div!(ctx::_Ctx, e::BinOp; solve::Bool = false)
    ld = _dims!(ctx, e.lhs)
    rd = _dims!(ctx, e.rhs)
    if solve
        (ld === nothing || rd === nothing) && return nothing
        return rd / ld
    end
    if rd === nothing && _scalar_value(ctx, e.rhs) !== nothing
        return ld
    elseif ld === nothing && _scalar_value(ctx, e.lhs) !== nothing
        rd === nothing && return nothing
        return Dims(ntuple(i -> -rd.exps[i], N_DIMENSIONS), 1.0 / rd.scale)
    end
    (ld === nothing || rd === nothing) && return nothing
    return ld / rd
end

"""`^` needs an integer exponent for a dimensioned base (plan 5.3). An exponent that is a
`@constants` integer folds to one; a dimensionless base may take any real exponent."""
function _pow!(ctx::_Ctx, e::BinOp)
    base = _dims!(ctx, e.lhs)
    exponent_value = _scalar_value(ctx, e.rhs)
    if exponent_value === nothing
        if base !== nothing && !is_dimensionless(base)
            _report!(
                ctx,
                "E006",
                "the exponent of [" * _label(ctx, e.lhs, base) *
                "] must be an integer literal" * _in_equation(ctx),
                e.rhs;
                hint = "write `x^2`, or use `sqrt(x)` for a square root",
            )
        end
        return nothing
    end
    base === nothing && return nothing
    if !isinteger(exponent_value)
        if is_dimensionless(base)
            return Dims(DIMENSIONLESS.exps, base.scale^exponent_value)
        end
        _report!(
            ctx,
            "E006",
            "the exponent of [" * _label(ctx, e.lhs, base) *
            "] must be an integer, found `" * _short(string(exponent_value), 24) * "`" *
            _in_equation(ctx),
            e.rhs;
            hint = "use `sqrt(x)` for a square root, or keep the exponent an integer literal",
        )
        return nothing
    end
    if abs(exponent_value) > 1e6
        _report!(
            ctx,
            "E006",
            "the exponent of [" * _label(ctx, e.lhs, base) *
            "] is too large to give a unit; keep it below 10^6" * _in_equation(ctx),
            e.rhs;
            hint = "a static exponent above 10^6 cannot produce a meaningful unit",
        )
        return nothing
    end
    return base^Int(exponent_value)
end

function _dims!(ctx::_Ctx, e::IfElse)
    _dims!(ctx, e.cond)
    return _common!(
        ctx,
        [(e.then, _dims!(ctx, e.then)), (e.otherwise, _dims!(ctx, e.otherwise))];
        what = "the branches of `ifelse` must have one unit",
    )
end

function _dims!(ctx::_Ctx, e::Comparison)
    ld = _dims!(ctx, e.lhs)
    rd = _dims!(ctx, e.rhs)
    if ld !== nothing && rd !== nothing
        if ld.exps != rd.exps
            _report!(
                ctx,
                "E006",
                "cannot compare [" * _label(ctx, e.rhs, rd) * "] with [" *
                _label(ctx, e.lhs, ld) * "]" * _in_equation(ctx),
                e.rhs;
                hint = "`" * _term_text(ctx, e.lhs) * "` is [" * _label(ctx, e.lhs, ld) *
                       "] but `" * _term_text(ctx, e.rhs) * "` is [" *
                       _label(ctx, e.rhs, rd) * "]",
            )
        else
            _scale_hint!(ctx, e.rhs, rd, e.lhs, ld)
        end
    end
    return nothing
end

function _dims!(ctx::_Ctx, e::BoolOp)
    for operand in e.operands
        _dims!(ctx, operand)
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------------------

"""Functions whose arguments must be dimensionless (plan 5.3: "functions need
dimensionless arguments"): the trig, exponential and rounding families plus `mod`/`rem`."""
const DIMENSIONLESS_ARG_FUNCS = (
    :sin, :cos, :tan, :asin, :acos, :atan, :sinh, :cosh, :tanh, :exp, :log, :log10,
    :floor, :ceil, :round, :mod, :rem,
)

"""Functions with "dimension in = dimension out" (plan 5.3's list) plus the library
signal shapers, which are in = out by definition. `sign` follows the plan literally:
the same dimension comes out as went in."""
const SAME_UNIT_FUNCS = (
    :abs, :sign, :min, :max, :clamp, :hypot, :deadzone, :saturate, :previous, :hold,
    :norm, :transpose,
)

"""Single-argument entries of `SAME_UNIT_FUNCS`."""
const SAME_UNIT_UNARY_FUNCS = (:abs, :sign, :previous, :hold, :norm, :transpose)

"""Walk every argument (for nested findings) and return `nothing` — the fallback for a call
whose arity is wrong (J1.1 reports E001) or whose unit rule is unknown."""
function _walk_args!(ctx::_Ctx, e::Call)
    for arg in e.args
        _dims!(ctx, arg)
    end
    return nothing
end

function _dims!(ctx::_Ctx, e::Call)
    name = e.fn.name
    args = e.args
    nargs = length(args)
    if name in DIMENSIONLESS_ARG_FUNCS
        for arg in args
            d = _dims!(ctx, arg)
            (d === nothing || is_dimensionless(d)) && continue
            _report!(
                ctx,
                "E006",
                "`" * String(name) * "` needs a dimensionless argument, got [" *
                _label(ctx, arg, d) * "]" * _in_equation(ctx),
                arg;
                hint = "divide by a reference value in the same unit, or use a unitless parameter",
            )
        end
        return DIMENSIONLESS
    elseif name === :sqrt && nargs == 1
        d = _dims!(ctx, args[1])
        d === nothing && return nothing
        if !all(iseven, d.exps)
            _report!(
                ctx,
                "E006",
                "`sqrt` needs even exponents, got [" * _label(ctx, args[1], d) * "]" *
                _in_equation(ctx),
                e;
                hint = "a square root needs even exponents (`m^2` gives `m`, `m` does not)",
            )
            return nothing
        end
        return Dims(ntuple(i -> d.exps[i] ÷ 2, N_DIMENSIONS), sqrt(d.scale))
    elseif name in SAME_UNIT_FUNCS
        if name in SAME_UNIT_UNARY_FUNCS
            nargs == 1 || return _walk_args!(ctx, e)
            return _dims!(ctx, args[1])
        end
        isempty(args) && return nothing
        return _common!(
            ctx,
            [(arg, _dims!(ctx, arg)) for arg in args];
            what = "`" * String(name) * "` arguments must have one unit",
        )
    elseif name === :dot && nargs == 2
        ld = _dims!(ctx, args[1])
        rd = _dims!(ctx, args[2])
        (ld === nothing || rd === nothing) && return nothing
        return ld * rd
    elseif name === :cross && nargs == 2
        return _common!(
            ctx,
            [(arg, _dims!(ctx, arg)) for arg in args];
            what = "`cross` arguments must have one unit",
        )
    elseif name === :ddt && nargs == 1
        d = _dims!(ctx, args[1])
        return d === nothing ? nothing : d / UNIT_S
    elseif name === :int && nargs == 2
        integrated = _dims!(ctx, args[1])
        start = _dims!(ctx, args[2])
        result = integrated === nothing ? nothing : integrated * UNIT_S
        if result !== nothing && start !== nothing && start.exps != result.exps
            _report!(
                ctx,
                "E006",
                "the start value of `int` is [" * _label(ctx, args[2], start) *
                "] but the integral is [" * unit_string(result) * "]" * _in_equation(ctx),
                args[2];
                hint = "the start value must have the integral's unit; a numeric literal like `0.0` is accepted in any unit",
            )
            return nothing
        end
        return result
    elseif name === :delay && nargs == 2
        d = _dims!(ctx, args[1])
        delay_dims = _dims!(ctx, args[2])
        if delay_dims !== nothing && delay_dims.exps != UNIT_S.exps
            _report!(
                ctx,
                "E006",
                "the delay time must be [s], got [" * _label(ctx, args[2], delay_dims) *
                "]" * _in_equation(ctx),
                args[2];
                hint = "the delay is a time; declare the parameter with `[unit = \"s\"]`",
            )
        end
        return d
    elseif name === :reinit && nargs == 2
        d = _dims!(ctx, args[1])
        value = _dims!(ctx, args[2])
        if d !== nothing && value !== nothing && d.exps != value.exps
            _report!(
                ctx,
                "E006",
                "`reinit` needs [" * _label(ctx, args[1], d) * "], got [" *
                _label(ctx, args[2], value) * "]" * _in_equation(ctx),
                args[2];
                hint = "reinit must assign a value in the variable's own unit",
            )
        end
        return nothing
    elseif name === :interp1 && nargs == 3
        u = _dims!(ctx, args[1])
        xs = _dims!(ctx, args[2])
        ys = _dims!(ctx, args[3])
        if u !== nothing && xs !== nothing && u.exps != xs.exps
            _report!(
                ctx,
                "E006",
                "`interp1` needs the query and the abscissa in one unit, got [" *
                _label(ctx, args[1], u) * "] and [" * _label(ctx, args[2], xs) * "]" *
                _in_equation(ctx),
                args[1];
                hint = "the query point and the table's abscissa must share a unit",
            )
            return nothing
        end
        return ys
    end
    # A call without a unit rule (an intrinsic such as `interp2`, or a function the
    # whitelist reports as E002): walk the arguments for nested findings, but make no
    # claim about the result.
    return _walk_args!(ctx, e)
end

# ---------------------------------------------------------------------------------------
# Equations
# ---------------------------------------------------------------------------------------

_item_scope(item) =
    hasproperty(item, :scope) && getproperty(item, :scope) isa Symbol ?
    getproperty(item, :scope) : :equations

function _check_item!(ctx::_Ctx, item)
    if item isa Equation
        _check_equation!(ctx, item)
    elseif item isa IfEquation
        for branch in item.branches
            branch.cond === nothing || _dims!(ctx, branch.cond)
            for sub in branch.body
                _check_item!(ctx, sub)
            end
        end
    elseif item isa ForEquation
        _for_each_iteration(ctx, item.var, item.lo, item.hi, item.step) do
            for sub in item.body
                _check_item!(ctx, sub)
            end
        end
    elseif item isa Assign
        _check_assign!(ctx, item)
    elseif item isa IfStatement
        for branch in item.branches
            branch.cond === nothing || _dims!(ctx, branch.cond)
            for sub in branch.body
                _check_item!(ctx, sub)
            end
        end
    elseif item isa ForStatement
        _for_each_iteration(ctx, item.var, item.lo, item.hi, item.step) do
            for sub in item.body
                _check_item!(ctx, sub)
            end
        end
    elseif item isa CallStatement
        _dims!(ctx, item.call)
    end
    return nothing
end

"""A discrete assignment needs equal units on both sides. The held value's own `unit`
attribute is the reference; a numeric literal on the right is legal in any unit."""
function _check_assign!(ctx::_Ctx, a::Assign)
    ctx.scope = a.scope
    ld = _dims!(ctx, a.target)
    if a.op === :assign
        rd = _dims!(ctx, a.value)
        result = rd
    else
        result = _dims!(ctx, BinOp(a.op, a.target, a.value, a.range))
    end
    if ld !== nothing && result !== nothing
        if ld.exps != result.exps
            _report!(
                ctx,
                "E006",
                "cannot assign [" * _label(ctx, a.value, result) * "] to [" *
                _label(ctx, a.target, ld) * "]" * _in_equation(ctx),
                a.value;
                hint = "`" * _term_text(ctx, a.target) * "` is [" *
                       _label(ctx, a.target, ld) * "] but `" * _term_text(ctx, a.value) *
                       "` is [" * _label(ctx, a.value, result) * "]",
            )
        else
            _scale_hint!(ctx, a.value, result, a.target, ld)
        end
    end
    return nothing
end

function _check_equation!(ctx::_Ctx, eq::Equation)
    ctx.scope = _item_scope(eq)
    ctx.text = ctx.pb === nothing ? "" : _short(_source_slice(ctx.pb, source_range(eq)))
    ld = _dims!(ctx, eq.lhs)
    rd = _dims!(ctx, eq.rhs)
    if ld !== nothing && rd !== nothing
        if ld.exps != rd.exps
            _report!(
                ctx,
                "E006",
                "cannot equate [" * _label(ctx, eq.rhs, rd) * "] with [" *
                _label(ctx, eq.lhs, ld) * "]" * _in_equation(ctx),
                eq.rhs;
                hint = "`" * _term_text(ctx, eq.lhs) * "` is [" * _label(ctx, eq.lhs, ld) *
                       "] but `" * _term_text(ctx, eq.rhs) * "` is [" *
                       _label(ctx, eq.rhs, rd) * "]",
            )
        else
            _scale_hint!(ctx, eq.rhs, rd, eq.lhs, ld)
        end
    end
    ctx.text = ""
    return nothing
end

# ---------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------

"""    check_units(pb::ParsedBlock[, domain::Symbol]) -> Vector{Diagnostic}

The unit pass of `check_block` (plan 4.4, check 6): parse every `unit` attribute, then
check every `@equations` item. Returns E006 for an inconsistency, an unparseable unit, or a
scale-only difference between two units of the same dimension.
Diagnostic sources point at the offending term (or at the declaration, for a bad unit
string) and messages name both units, e.g.

    cannot add [m/s] to [N] in "F ~ k*x + v"

`domain` is the adopted domain of the instance (plan 5.6). The flattener calls
`check_units(pb, adopted)` for a `Generic` block once its bond island has adopted a concrete
domain (D9), so the check runs against the substituted units and a message quotes the
concrete text (`[F]`, `[m/N]`) rather than `[flow*s/effort]`. It defaults to
[`block_domain`](@ref)`(pb)`, which is what the block-level check passes.

The function is total: bad input produces diagnostics, never an exception. There is
deliberately no `(block_interface, equations)` overload — without a `ParsedBlock` there is
no `SourceRange`, and a diagnostic that cannot point at user code would break spec
principle 6.
"""
function check_units(
    pb::ParsedBlock,
    domain::Symbol = block_domain(pb),
)::Vector{Diagnostic}
    diags = Diagnostic[]
    env = _build_env(pb, diags, domain)
    ctx = _Ctx(env, pb, diags, true, :equations, "", Dict{Symbol,Int}())
    for item in equations(pb)
        _check_item!(ctx, item)
    end
    ctx.scope = :initial
    for item in initial_equations(pb)
        _check_item!(ctx, item)
    end
    ctx.scope = :discrete
    for ds in discrete_scopes(pb), item in discrete_body(ds)
        _check_item!(ctx, item)
    end
    ctx.scope = :events
    for ev in events(pb)
        _dims!(ctx, ev.cond)
        for item in ev.body
            _check_item!(ctx, item)
        end
    end
    ctx.text = ""
    return ctx.diags
end

export
    check_units,
    dims_of,
    unit_env,
    block_domain,
    parse_unit,
    unit_string,
    conversion_factor,
    substitute_domain,
    effort_dims,
    flow_dims,
    effort_component_dims,
    flow_component_dims,
    power_dims,
    component_count,
    is_multibond_domain,
    domain_effort_unit_strings,
    domain_flow_unit_strings,
    Dims,
    UnitEnv,
    UnitParseError,
    UNIT_TABLE,
    DIMENSIONLESS,
    DIMENSION_NAMES,
    exponent,
    exponents,
    scale_of,
    with_scale,
    is_dimensionless,
    has_pseudo_dimensions
