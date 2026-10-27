# The bg-sim AST.
#
# This file is the contract for every later stage of the front end: the unit checker
# (`src/units/`, J1.2), the library catalog (`src/library/`, J1.3) and flattening
# (`src/ir/`, J1.4) walk these nodes and must not reach into fields directly. The public
# accessors are listed at the bottom; the types themselves are `BGSim.`-qualified (they are
# deliberately not exported, because `Name`, `Call` and `Index` are too common to export).
#
# Design rules:
#   * Small, immutable structs. Every node carries a `SourceRange`, so a diagnostic can
#     always point at user code (spec principle 6).
#   * The AST records *syntax*, not semantics. `Call` holds any function name and `BinOp`
#     any operator; the whitelist (`whitelist.jl`) decides what is allowed, in `check_block`.
#   * `Expr` is the abstract supertype of expression nodes. The node kinds are
#     `Lit`, `Name`, `Field`, `Call`, `BinOp`, `UnOp`, `Index`, `VectorLit`, `MatrixLit`,
#     `IfElse`, `Comparison` and `BoolOp`. `Field` is the one addition to the list in the
#     work-package brief: the spec needs `p.e` / `p.f`, and flattening must see the port and
#     the field separately rather than parse a dotted string.
#   * Types are data, never strings: `TypeSpec(:Vec, (3,))` is `Vec{3}`. A size may stay a
#     `Symbol` (`Vec{N}`) until the structural constant is resolved, because decision D13
#     lets an instance override `N`.
#   * Nothing here is produced by `eval`: `parse.jl` walks JuliaSyntax nodes and builds
#     these values; `constfold.jl` folds the constant expressions.
#
# Statement-level items in `@equations` / `@initial` are `Equation`, `IfEquation` or
# `ForEquation`. `@discrete` bodies hold `Assign`, `IfStatement`, `ForStatement` and
# `CallStatement` nodes; an `@events` entry is one `EventDecl`, and a `@discrete` scope is one
# `DiscreteScope`. Declarations are `Decl`; `@causality` entries are `CausalityDecl`.

"""    Expr

Abstract supertype of every expression node. See the file header for the node list.
`expr_range(e)` gives the node's source range."""
abstract type Expr end

"""    Lit(value, range)

A literal: `Float64`, `Int`, `Bool` or `String`. Strings are only legal in the `unit` and
`description` attributes; the checker rejects them elsewhere."""
struct Lit <: Expr
    value::Any
    range::SourceRange
end

"""    Name(name, range)

A bare identifier: a declaration, `t`, a loop variable, or an undeclared name (the check
stage reports E003 for the last)."""
struct Name <: Expr
    name::Symbol
    range::SourceRange
end

"""    Field(base, field, range)

Dotted access, `p.e` or `p.f`, where `base` is normally a `Name` that names a power port."""
struct Field <: Expr
    base::Expr
    field::Symbol
    range::SourceRange
end

"""    Call(fn, args, range)

A function call. `fn` is a `Name`, so `expr_range(call.fn)` is exactly the name range — that
is what E002 points at. Any name may appear here; the whitelist decides in `check_block`."""
struct Call <: Expr
    fn::Name
    args::Vector{Expr}
    range::SourceRange
end

"""    BinOp(op, lhs, rhs, range)

A binary operator: `+ - * / \\ ^ %` and friends. The whitelist decides which are allowed;
`%`, `÷` and `//` are rejected with E002 (use `mod` / `rem`)."""
struct BinOp <: Expr
    op::Symbol
    lhs::Expr
    rhs::Expr
    range::SourceRange
end

"""    UnOp(op, operand, range)

A unary operator: `-`, `+` or `!`."""
struct UnOp <: Expr
    op::Symbol
    operand::Expr
    range::SourceRange
end

"""    Index(base, indices, range)

`v[i]`, `P[i, j]`. Static (literal) indices are range-checked against a known size (E005);
symbolic indices are accepted and checked by J2.1 when loops are unrolled."""
struct Index <: Expr
    base::Expr
    indices::Vector{Expr}
    range::SourceRange
end

"""    VectorLit(elements, range)

`[1.0, 2.0]`."""
struct VectorLit <: Expr
    elements::Vector{Expr}
    range::SourceRange
end

"""    MatrixLit(rows, range)

`[1 2; 3 4]`, stored row by row."""
struct MatrixLit <: Expr
    rows::Vector{Vector{Expr}}
    range::SourceRange
end

"""    IfElse(cond, then, otherwise, range)

`ifelse(cond, a, b)`, the only conditional allowed inside an expression."""
struct IfElse <: Expr
    cond::Expr
    then::Expr
    otherwise::Expr
    range::SourceRange
end

"""    Comparison(op, lhs, rhs, range)

`== != < <= > >=`. In `@equations` a comparison is only allowed as the condition of an
`ifelse`; the checker reports E001 elsewhere."""
struct Comparison <: Expr
    op::Symbol
    lhs::Expr
    rhs::Expr
    range::SourceRange
end

"""    BoolOp(op, operands, range)

`&&`, `||` or `!`. Like `Comparison`, only allowed inside an `ifelse` condition in
`@equations`."""
struct BoolOp <: Expr
    op::Symbol
    operands::Vector{Expr}
    range::SourceRange
end

expr_range(e::Expr) = e.range
source_range(e::Expr) = e.range

# ---------------------------------------------------------------------------------------
# Types as data
# ---------------------------------------------------------------------------------------

"""
    TypeSpec(kind, args)

A declared or inferred type, as data:

| written | `kind` | `args` |
| --- | --- | --- |
| `Real` | `:Real` | `()` |
| `Int` | `:Int` | `()` |
| `Bool` | `:Bool` | `()` |
| `Vec{N}` | `:Vec` | `(N,)` |
| `Mat{N,M}` | `:Mat` | `(N,M)` |
| `Power{Rotation}` | `:Power` | `(:Rotation,)` |

A size argument is an `Int` when it is literal or resolved from a `@constants` value and a
`Symbol` while it is still `N` (decision D13: an instance may override it). Use
[`type_name`](@ref) for display, [`type_size`](@ref) for the JSON shape and
[`resolve_type`](@ref) to substitute structural constants.
"""
struct TypeSpec
    kind::Symbol
    args::Tuple{Vararg{Any}}
end

TypeSpec(kind::Symbol) = TypeSpec(kind, ())

const REAL = TypeSpec(:Real)
const INT = TypeSpec(:Int)
const BOOL = TypeSpec(:Bool)

type_kind(t::TypeSpec) = t.kind
type_args(t::TypeSpec) = t.args

"""    type_name(t) -> String

The source spelling, e.g. `"Vec{N}"`, `"Mat{3,3}"`, `"Power{Generic}"`."""
function type_name(t::TypeSpec)::String
    t.kind in (:Real, :Int, :Bool) && return String(t.kind)
    if t.kind == :Vec
        return "Vec{" * _argname(t.args[1]) * "}"
    elseif t.kind == :Mat
        return "Mat{" * _argname(t.args[1]) * "," * _argname(t.args[2]) * "}"
    elseif t.kind == :Power
        return "Power{" * _argname(t.args[1]) * "}"
    end
    return String(t.kind)
end

_argname(x::Symbol) = String(x)
_argname(x::Integer) = string(Int(x))
_argname(x) = string(x)

"""    type_element(t) -> Symbol

The scalar element type: `:Real` for `Vec`/`Mat` (both are `Float64` arrays per the spec),
otherwise the scalar kind."""
type_element(t::TypeSpec)::Symbol = t.kind in (:Vec, :Mat) ? :Real : t.kind

"""    is_scalar_type(t) -> Bool

True for `Real`, `Int` and `Bool`."""
is_scalar_type(t::TypeSpec) = t.kind in (:Real, :Int, :Bool)

"""    is_array_type(t) -> Bool

True for `Vec` and `Mat`."""
is_array_type(t::TypeSpec) = t.kind in (:Vec, :Mat)

"""    type_domain(t) -> Union{Symbol,Nothing}

The domain of a `Power{Domain}` port type, else `nothing`."""
type_domain(t::TypeSpec) = t.kind == :Power && !isempty(t.args) ? t.args[1] : nothing

"""    resolve_type(t, env) -> TypeSpec

Substitute `Symbol` size arguments from `env` (a map from structural constant to value).
Unresolved symbols stay symbols; the checker reports E005 for those.
"""
function resolve_type(t::TypeSpec, env::AbstractDict)::TypeSpec
    isempty(t.args) && return t
    resolved = map(t.args) do a
        if a isa Symbol && haskey(env, a) && env[a] isa Integer
            return Int(env[a])
        elseif a isa Expr
            # A size written as `ifelse(cond, a, b)` (the spec allows it in sizes).
            ok, value = try_eval_const(a, env)
            return ok && value isa Integer ? Int(value) : a
        end
        return a
    end
    return TypeSpec(t.kind, Tuple(resolved))
end

"""    type_size(t, env = Dict()) -> Union{Vector{Int},Nothing}

The JSON `size` of the declaration: `Int[]` for a scalar, `[N]` for `Vec{N}`, `[N,M]` for
`Mat{N,M}`, and `nothing` when a size is not static (which the checker reports as E005).
"""
function type_size(t::TypeSpec, env::AbstractDict = Dict{Symbol,Any}())
    is_scalar_type(t) && return Int[]
    t.kind == :Power && return Int[]  # the port size comes from the domain, not the type
    resolved = resolve_type(t, env)
    if t.kind == :Vec
        a = resolved.args[1]
        return a isa Integer ? Int[Int(a)] : nothing
    elseif t.kind == :Mat
        a, b = resolved.args[1], resolved.args[2]
        return a isa Integer && b isa Integer ? Int[Int(a), Int(b)] : nothing
    end
    return nothing
end

"""    type_scalar_count(t, env = Dict()) -> Int

The number of scalars a declaration of this type expands to (1 for a scalar, `prod(size)`
for an array, the domain size for a port).
"""
function type_scalar_count(t::TypeSpec, env::AbstractDict = Dict{Symbol,Any}())::Int
    t.kind == :Power && return domain_size(type_domain(t))
    sz = type_size(t, env)
    sz === nothing && return 1
    return isempty(sz) ? 1 : prod(sz)
end

"""    domain_size(domain) -> Int

Port size per domain (spec "Types and domains"): 1 for the scalar domains, 3 for `Planar`,
6 for `Spatial` and 1 for `Generic` (adopted from its first concrete connection).
"""
domain_size(::Nothing) = 1
function domain_size(d::Symbol)::Int
    d === :Planar && return 3
    d === :Spatial && return 6
    return 1
end

# ---------------------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------------------

"""
    Decl(name, type, default, attrs, scope, range, default_text)

One declaration. `type` is a [`TypeSpec`](@ref); `default` is the default-value expression
(an `Expr`) or `nothing`; `attrs` holds the evaluated attributes:

| key | value |
| --- | --- |
| `:unit` | `String` |
| `:min`, `:max`, `:nominal` | `Int` or `Float64` |
| `:tunable` | `Bool` |
| `:description` | `String` |
| `:state` | `:prefer` or `:avoid` |
| `:options` | `Vector{String}` |
| `:structural` | `Bool` |

`default_text` is the default's original source text, which is what the catalog reports
(`parameterDecl.default`, plan 3.2) so that `1e-3` stays `1e-3`.
"""
struct Decl
    name::Symbol
    type::TypeSpec
    default::Union{Expr,Nothing}
    attrs::Dict{Symbol,Any}
    scope::Symbol
    range::SourceRange
    default_text::Union{String,Nothing}
end

decl_name(d::Decl) = d.name
decl_type(d::Decl) = d.type
decl_default(d::Decl) = d.default
decl_attrs(d::Decl) = d.attrs
decl_scope(d::Decl) = d.scope
decl_range(d::Decl) = d.range
decl_default_text(d::Decl) = d.default_text
source_range(d::Decl) = d.range

# ---------------------------------------------------------------------------------------
# Equations
# ---------------------------------------------------------------------------------------

"""    Equation(lhs, rhs, range, scope)

`lhs ~ rhs` in `@equations` (or later `@initial`). `scope` is `:equations` / `:initial`."""
struct Equation
    lhs::Expr
    rhs::Expr
    range::SourceRange
    scope::Symbol
end

source_range(e::Equation) = e.range

"""    EqBranch(cond, body, range)

One branch of an `if` in `@equations`. `cond` is `nothing` for the `else` branch."""
struct EqBranch
    cond::Union{Expr,Nothing}
    body::Vector{Any}
    range::SourceRange
end

source_range(b::EqBranch) = b.range

"""    IfEquation(branches, range)

`if / elseif / else` around whole equations. Every branch must hold the same number of
equations (spec table, "if / elseif / else") and an `else` branch is required (plan 4.4:
the balance count must be the same whichever branch runs)."""
struct IfEquation
    branches::Vector{EqBranch}
    range::SourceRange
end

source_range(e::IfEquation) = e.range

"""    ForEquation(var, lo, hi, step, body, range)

`for var in lo:hi` or `for var in lo:step:hi`. `lo` and `hi` must be constant (E005
otherwise) and the body is unrolled for the balance count."""
struct ForEquation
    var::Symbol
    lo::Expr
    hi::Expr
    step::Union{Expr,Nothing}
    body::Vector{Any}
    range::SourceRange
end

source_range(e::ForEquation) = e.range

# ---------------------------------------------------------------------------------------
# Discrete statements, event entries and the @discrete scope (J2.1)
# ---------------------------------------------------------------------------------------
#
# `@discrete` and `@events` are imperative: their bodies are *statement* lists, not
# equations. The nodes below mirror the equation nodes, but a statement is executed in
# order (plan D18, D19, D21).

"""    Assign(target, value, op, range, scope)

One assignment in `@discrete` or `@events`: `target = value`, or the compound form
`target += value` with `op = :+` (`:assign` marks plain `=`). `target` is a `Name` or an
`Index`; the checker decides whether it names a declared held value (a `@variables` or
`@outputs` entry) or a D18 block-local temporary. `scope` is `:discrete` or `:events`."""
struct Assign
    target::Expr
    value::Expr
    op::Symbol
    range::SourceRange
    scope::Symbol
end

source_range(a::Assign) = a.range
assign_target(a::Assign) = a.target
assign_value(a::Assign) = a.value
assign_op(a::Assign) = a.op

"""    is_compound_assign(a) -> Bool

True for `+=`, `-=`, `*=` and `/=`."""
is_compound_assign(a::Assign) = a.op !== :assign

"""    StmtBranch(cond, body, range)

One branch of an `if` statement in discrete code. `cond` is `nothing` for the `else`
branch; `body` is a `Vector{Any}` of statement nodes."""
struct StmtBranch
    cond::Union{Expr,Nothing}
    body::Vector{Any}
    range::SourceRange
end

source_range(b::StmtBranch) = b.range

"""    IfStatement(branches, range, scope)

`if / elseif / else` inside `@discrete` or `@events`. Unlike `IfEquation` the branches may
hold different numbers of statements: discrete code is imperative."""
struct IfStatement
    branches::Vector{StmtBranch}
    range::SourceRange
    scope::Symbol
end

source_range(s::IfStatement) = s.range

"""    ForStatement(var, lo, hi, step, body, range, scope)

`for var in lo:hi` inside `@discrete` or `@events`. `lo`, `hi` and `step` must fold to
integers (E005 otherwise); the body is a statement list."""
struct ForStatement
    var::Symbol
    lo::Expr
    hi::Expr
    step::Union{Expr,Nothing}
    body::Vector{Any}
    range::SourceRange
    scope::Symbol
end

source_range(s::ForStatement) = s.range

"""    CallStatement(call, range, scope)

A call used as a statement. Only `reinit(x, value)` is meaningful (and only in `@events`);
the checker rejects every other bare call."""
struct CallStatement
    call::Call
    range::SourceRange
    scope::Symbol
end

source_range(s::CallStatement) = s.range
stmt_call(s::CallStatement) = s.call

"""    EventDecl(cond, body, range)

One `cond => begin ... end` entry of `@events` (plan D19). `cond` is either a real
expression (an upward zero crossing) or a `Comparison` with `<` / `>`; `body` is a
statement list. Events are order-free across entries but ordered inside one body."""
struct EventDecl
    cond::Expr
    body::Vector{Any}
    range::SourceRange
end

source_range(e::EventDecl) = e.range
event_condition(e::EventDecl) = e.cond
event_body(e::EventDecl) = copy(e.body)

"""
    event_zero_crossing(e::EventDecl) -> Expr

The real expression whose **upward zero crossing** fires `e` (plan D19): the condition
itself, or for a comparison the normalized difference — `a < b` becomes `b - a` and
`a > b` becomes `a - b`. J2.3 lowers this expression; `event_condition` keeps the source
form for diagnostics and editor display.
"""
function event_zero_crossing(e::EventDecl)
    c = e.cond
    if c isa Comparison
        if c.op === :<
            return BinOp(:-, c.rhs, c.lhs, c.range)
        elseif c.op === :>
            return BinOp(:-, c.lhs, c.rhs, c.range)
        end
    end
    return c
end

"""    DiscreteScope(period, offset, body, range, period_value, offset_value)

One `@discrete Ts = <period> begin ... end` scope. `period` and `offset` are the parsed
constant expressions; `period_value` / `offset_value` are their folded values (`nothing`
when the expression does not fold, which `check_block` reports as E004). `Ts` names
`period_value` inside the body."""
struct DiscreteScope
    period::Expr
    offset::Union{Expr,Nothing}
    body::Vector{Any}
    range::SourceRange
    period_value::Union{Float64,Nothing}
    offset_value::Union{Float64,Nothing}
end

source_range(d::DiscreteScope) = d.range
discrete_period(d::DiscreteScope) = d.period_value
discrete_offset(d::DiscreteScope) = d.offset_value
discrete_body(d::DiscreteScope) = copy(d.body)

# ---------------------------------------------------------------------------------------
# Causality
# ---------------------------------------------------------------------------------------

"""
    CausalityDecl(ports, kind, value, range)

One `@causality` entry, in the catalog's terms (plan D6 / plan 3.2):

| written | `ports` | `kind` | `value` |
| --- | --- | --- | --- |
| `p => :effort_out` | `[:p]` | `:preferred` | `:effort_out` |
| `p => :flow_out` | `[:p]` | `:preferred` | `:flow_out` |
| `p => (:effort_out, :fixed)` | `[:p]` | `:fixed` | `:effort_out` |
| `(p1, p2) => :transformer` | `[:p1, :p2]` | `:transformer` | `nothing` |
| `(p1, p2) => :gyrator` | `[:p1, :p2]` | `:gyrator` | `nothing` |
"""
struct CausalityDecl
    ports::Vector{Symbol}
    kind::Symbol
    value::Union{Symbol,Nothing}
    range::SourceRange
end

causality_ports(c::CausalityDecl) = c.ports
causality_kind(c::CausalityDecl) = c.kind
causality_value(c::CausalityDecl) = c.value
source_range(c::CausalityDecl) = c.range

# ---------------------------------------------------------------------------------------
# Textual subsystems: @components / @connections (J2.6, decision D5)
# ---------------------------------------------------------------------------------------

"""
    ComponentDecl(name, block, kwargs, range)

One `name = BlockName(kw = expression, ...)` entry of `@components`. `block` is the
referenced block *name* as written (a project or stdlib block is resolved by name at
instantiation); `kwargs` are the parameter overrides in source order, as `(name, expr)`
pairs in the defaults expression scope.
"""
struct ComponentDecl
    name::Symbol
    block::Symbol
    kwargs::Vector{Pair{Symbol,Expr}}
    range::SourceRange
end

component_name(c::ComponentDecl) = c.name
component_block(c::ComponentDecl) = c.block
component_kwargs(c::ComponentDecl) = copy(c.kwargs)
source_range(c::ComponentDecl) = c.range

"""
    PortRef(instance, port, range)

One side of a `connect(...)`: a port of the block itself (`instance === nothing`) or a port
of one of its `@components` (`instance` names the component).
"""
struct PortRef
    instance::Union{Symbol,Nothing}
    port::Symbol
    range::SourceRange
end

portref_instance(p::PortRef) = p.instance
portref_port(p::PortRef) = p.port
source_range(p::PortRef) = p.range

"""
    ConnectDecl(from, to, range)

One `connect(a, b)` entry of `@connections`. The order is the source order; it decides which
end is the bond's positive-power end when the connection is a bond.
"""
struct ConnectDecl
    from::PortRef
    to::PortRef
    range::SourceRange
end

connect_from(c::ConnectDecl) = c.from
connect_to(c::ConnectDecl) = c.to
source_range(c::ConnectDecl) = c.range

# ---------------------------------------------------------------------------------------
# The parsed block
# ---------------------------------------------------------------------------------------

"""
    ParsedBlock

The result of [`parse_block`](@ref): the block's name, its reference and source text, its
declarations per scope, its equations (continuous and initial), its `@discrete` scopes and
`@events` entries, its causality declarations, its `@components` / `@connections` textual
subsystem (J2.6), and the diagnostics the parser itself produced (E000 and structural E001).
`check_block` adds the semantic checks.

Accessors (do not read the fields directly):
[`block_name`](@ref), [`block_ref`](@ref), [`block_source`](@ref), [`scopes`](@ref),
[`declarations`](@ref), [`equations`](@ref), [`initial_equations`](@ref),
[`discrete_scopes`](@ref), [`events`](@ref), [`causality`](@ref), [`ports`](@ref),
[`components`](@ref), [`connections`](@ref),
[`block_range`](@ref), [`block_filename`](@ref), [`block_diagnostics`](@ref).
"""
struct ParsedBlock
    name::Symbol
    ref::String
    source::String
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
end

block_name(pb::ParsedBlock) = pb.name
block_ref(pb::ParsedBlock) = pb.ref
block_source(pb::ParsedBlock) = pb.source
block_filename(pb::ParsedBlock) = pb.filename
block_range(pb::ParsedBlock) = pb.range
block_diagnostics(pb::ParsedBlock) = pb.diagnostics

"""    scopes(pb) -> Vector{Symbol}

The scopes that appear in the block, in source order, as plain symbols: `:parameters`,
`:equations`, ... (use `scope_string(:equations) == "@equations"` for display)."""
scopes(pb::ParsedBlock) = copy(pb.scope_list)

"""    declarations(pb, scope::Symbol) -> Vector{Decl}

The declarations of one scope (`:constants`, `:parameters`, `:inputs`, `:outputs`,
`:ports`, `:variables`), in source order. The dictionary behind it always has all six keys."""
function declarations(pb::ParsedBlock, scope::Symbol)::Vector{Decl}
    return copy(get(pb.declaration_map, scope, Decl[]))
end

"""    equations(pb) -> Vector{Any}

The top-level `@equations` items: `Equation`, `IfEquation` and `ForEquation` nodes. This is
the unchecked AST; use [`block_equations`](@ref) for the checked list."""
equations(pb::ParsedBlock) = copy(pb.equation_items)

"""    initial_equations(pb) -> Vector{Any}

The top-level `@initial` items: `Equation`, `IfEquation` and `ForEquation` nodes with
`scope == :initial`. Like [`equations`](@ref) this is the unchecked AST."""
initial_equations(pb::ParsedBlock) = copy(pb.initial_items)

"""    discrete_scopes(pb) -> Vector{DiscreteScope}

Every `@discrete` scope in source order. A block may have more than one (multi-rate
discrete code); each carries its folded period and optional offset."""
discrete_scopes(pb::ParsedBlock) = copy(pb.discrete_items)

"""    events(pb) -> Vector{EventDecl}

Every `cond => begin ... end` entry of every `@events` scope, in source order."""
events(pb::ParsedBlock) = copy(pb.event_items)

"""    causality(pb) -> Vector{CausalityDecl}

The `@causality` entries in source order."""
causality(pb::ParsedBlock) = copy(pb.causality_items)

"""    ports(pb) -> Vector{Decl}

The `@ports` declarations in source order (each has a `Power{Domain}` type)."""
ports(pb::ParsedBlock) = declarations(pb, :ports)

"""    components(pb) -> Vector{ComponentDecl}

Every `@components` entry in source order; empty for a block without the scope. This is the
textual subsystem's instance list (decision D5)."""
components(pb::ParsedBlock) = copy(pb.component_items)

"""    connections(pb) -> Vector{ConnectDecl}

Every `connect(a, b)` entry of `@connections` in source order; empty for a block without the
scope."""
connections(pb::ParsedBlock) = copy(pb.connection_items)

"""    scope_string(scope::Symbol) -> String

`scope_string(:equations) == "@equations"` — the spelling used in diagnostics."""
scope_string(scope::Symbol) = "@" * String(scope)

# ---------------------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------------------

function Base.show(io::IO, e::Lit)
    show(io, e.value)
end
function Base.show(io::IO, e::Name)
    print(io, e.name)
end
function Base.show(io::IO, e::Field)
    show(io, e.base)
    print(io, '.', e.field)
end
function Base.show(io::IO, e::Call)
    print(io, e.fn.name, '(')
    for (i, a) in enumerate(e.args)
        i > 1 && print(io, ", ")
        show(io, a)
    end
    print(io, ')')
end
function Base.show(io::IO, e::BinOp)
    print(io, '(')
    show(io, e.lhs)
    print(io, ' ', e.op, ' ')
    show(io, e.rhs)
    print(io, ')')
end
function Base.show(io::IO, e::UnOp)
    print(io, '(', e.op)
    show(io, e.operand)
    print(io, ')')
end
function Base.show(io::IO, e::Index)
    show(io, e.base)
    print(io, '[')
    for (i, a) in enumerate(e.indices)
        i > 1 && print(io, ", ")
        show(io, a)
    end
    print(io, ']')
end
function Base.show(io::IO, e::VectorLit)
    print(io, '[')
    for (i, a) in enumerate(e.elements)
        i > 1 && print(io, ", ")
        show(io, a)
    end
    print(io, ']')
end
function Base.show(io::IO, e::MatrixLit)
    print(io, '[')
    for (r, row) in enumerate(e.rows)
        r > 1 && print(io, "; ")
        for (c, a) in enumerate(row)
            c > 1 && print(io, ' ')
            show(io, a)
        end
    end
    print(io, ']')
end
function Base.show(io::IO, e::IfElse)
    print(io, "ifelse(")
    show(io, e.cond)
    print(io, ", ")
    show(io, e.then)
    print(io, ", ")
    show(io, e.otherwise)
    print(io, ')')
end
function Base.show(io::IO, e::Comparison)
    print(io, '(')
    show(io, e.lhs)
    print(io, ' ', e.op, ' ')
    show(io, e.rhs)
    print(io, ')')
end
function Base.show(io::IO, e::BoolOp)
    print(io, '(')
    for (i, a) in enumerate(e.operands)
        i > 1 && print(io, ' ', e.op, ' ')
        show(io, a)
    end
    print(io, ')')
end
function Base.show(io::IO, e::Equation)
    show(io, e.lhs)
    print(io, " ~ ")
    show(io, e.rhs)
end
function Base.show(io::IO, d::Decl)
    print(io, d.name, "::", type_name(d.type))
    d.default === nothing || (print(io, " = "); show(io, d.default))
end
function Base.show(io::IO, c::CausalityDecl)
    print(io, '(', join(string.(c.ports), ", "), ") => ", c.kind)
    c.value === nothing || print(io, '/', c.value)
end

# ---------------------------------------------------------------------------------------
# The `diag` bridge to parsed blocks
# ---------------------------------------------------------------------------------------

"""
    diag(code, message, pb::ParsedBlock, node; scope, hint, ...) -> Diagnostic

Build a diagnostic that points at `node` in `pb`: `block` is filled from the block ref and
`source` from the node's range. `scope` may be a `Symbol` (`:equations`) or a `String`
(`"@equations"`); it defaults to the node's own scope when the node has one.
"""
function diag(
    code::AbstractString,
    message::AbstractString,
    pb::ParsedBlock,
    node;
    scope = nothing,
    hint = nothing,
    path = nothing,
    node_id = nothing,
    connection = nothing,
    related = Related[],
    severity = nothing,
)
    r = source_range(node)
    kind = source_kind(pb.ref)
    src = SourceRef(kind, pb.ref, r)
    scope_str = scope === nothing ? _node_scope(node) : _scope_kw(scope)
    return diag(
        code,
        message;
        hint = hint,
        path = path,
        block = pb.ref,
        scope = scope_str,
        source = src,
        node = node_id,
        connection = connection,
        related = related,
        severity = severity,
    )
end

_scope_kw(scope::Symbol) = scope_string(scope)
_scope_kw(scope::AbstractString) = String(scope)
_scope_kw(::Nothing) = nothing

_node_scope(node::Decl) = scope_string(node.scope)
_node_scope(node::Equation) = scope_string(node.scope)
_node_scope(node::Assign) = scope_string(node.scope)
_node_scope(node::IfStatement) = scope_string(node.scope)
_node_scope(node::ForStatement) = scope_string(node.scope)
_node_scope(node::CallStatement) = scope_string(node.scope)
_node_scope(::Any) = nothing
