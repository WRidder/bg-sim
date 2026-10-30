# The whitelist: the single table that decides what the language accepts (spec section
# "Operators and statements per scope" and "Built-in function whitelist", row by row).
#
# Nothing else in the front end may hard-code "is this allowed?": the parser only refuses
# syntax it cannot represent, and `check_block` asks this file. Every row carries a lowering
# rule tag for J1.4 (`:inline_ops`, `:ddt`, `:unroll_for`, ...).
#
# Contexts (the columns of the spec table):
#   :equation  — an expression in `@equations` (and later `@initial`)
#   :discrete  — an expression or statement in `@discrete` / `@events` (J2.1)
#   :default   — a declaration default, a size or an attribute value
# The spec's "All" column is `ALL_CONTEXTS`.
#
# `only_in_ifelse = true` encodes the spec's "Inside `ifelse` only" cell: in `@equations`
# and in defaults, comparisons and `&& || !` are legal only as the condition of an `ifelse`.

const ALL_CONTEXTS = Symbol[:equation, :discrete, :default]

struct FunctionRule
    names::Vector{Symbol}
    contexts::Vector{Symbol}
    min_args::Int
    max_args::Int          # -1 means variadic
    lowering::Symbol
    stdlib_only::Bool
end

FunctionRule(names, contexts, min_args, max_args, lowering; stdlib_only = false) =
    FunctionRule(
        Symbol[Symbol(n) for n in names],
        Symbol[Symbol(c) for c in contexts],
        min_args,
        max_args,
        lowering,
        stdlib_only,
    )

"""
    IntrinsicRule(name, contexts, min_args, max_args, stdlib_only, lowering)

The D12 intrinsics table. Intrinsics are opaque registered functions: `interp1` and
`interp2` are callable from user code, `noise_normal` and `delay` only from blocks under
`stdlib/` (`stdlib_only = true`). The rows are the single source: `FUNCTION_RULES` includes
one `FunctionRule` built from each of them, so `function_rule` sees exactly one table.

| intrinsic | scopes | user-callable |
| --- | --- | --- |
| `interp1(u, xs, ys)` | all | yes |
| `interp2(u, v, xs, ys)` | all | yes |
| `noise_normal(seed, k)` | discrete | no |
| `csv_value(table, k, t)` | all | no (F5.1, `CsvSource` only) |
| `delay(x, T)` | equations | no |
"""
struct IntrinsicRule
    name::Symbol
    contexts::Vector{Symbol}
    min_args::Int
    max_args::Int
    stdlib_only::Bool
    lowering::Symbol
end

const INTRINSIC_RULES = IntrinsicRule[
    IntrinsicRule(:interp1, ALL_CONTEXTS, 3, 3, false, :intrinsic),
    IntrinsicRule(:interp2, ALL_CONTEXTS, 4, 4, false, :intrinsic),
    IntrinsicRule(:noise_normal, [:discrete], 2, 2, true, :intrinsic),
    IntrinsicRule(:csv_value, ALL_CONTEXTS, 3, 3, true, :intrinsic),
    IntrinsicRule(:delay, [:equation], 2, 2, true, :delay),
]

"""    intrinsic_rule(name::Symbol) -> Union{IntrinsicRule,Nothing}

The D12 row for an intrinsic name, or `nothing` for an ordinary whitelisted function."""
function intrinsic_rule(name::Symbol)
    for rule in INTRINSIC_RULES
        rule.name === name && return rule
    end
    return nothing
end

"""The non-intrinsic rows of the spec's built-in function table."""
const BASE_FUNCTION_RULES = FunctionRule[
    FunctionRule([:sin, :cos, :tan], ALL_CONTEXTS, 1, 1, :math),
    FunctionRule([:asin, :acos, :atan], ALL_CONTEXTS, 1, 2, :math),
    FunctionRule([:sinh, :cosh, :tanh], ALL_CONTEXTS, 1, 1, :math),
    FunctionRule([:exp, :log, :log10, :sqrt], ALL_CONTEXTS, 1, 1, :math),
    FunctionRule([:abs, :sign], ALL_CONTEXTS, 1, 1, :nonsmooth),
    FunctionRule([:min, :max, :clamp], ALL_CONTEXTS, 2, 3, :nonsmooth),
    FunctionRule([:floor, :ceil, :round], ALL_CONTEXTS, 1, 1, :discontinuous),
    FunctionRule([:mod, :rem], ALL_CONTEXTS, 2, 2, :math),
    FunctionRule([:hypot], ALL_CONTEXTS, 2, 2, :math),
    FunctionRule([:dot], ALL_CONTEXTS, 2, 2, :linear_algebra),
    FunctionRule([:norm], ALL_CONTEXTS, 1, 1, :linear_algebra),
    FunctionRule([:cross], ALL_CONTEXTS, 2, 2, :linear_algebra),
    FunctionRule([:transpose], ALL_CONTEXTS, 1, 1, :static_array),
    FunctionRule([:ddt], [:equation], 1, 1, :derivative),
    FunctionRule([:int], [:equation], 2, 2, :integral),
    FunctionRule([:deadzone, :saturate], ALL_CONTEXTS, 2, 3, :library),
    FunctionRule([:previous], [:discrete], 1, 1, :sample_previous),
    FunctionRule([:hold], [:discrete], 1, 1, :sample_hold),
    FunctionRule([:reinit], [:events], 2, 2, :reset),
]

"""
The built-in function whitelist (spec table "Built-in function whitelist"), including the
D12 intrinsics from [`INTRINSIC_RULES`](@ref). `stdlib_only` restricts a call to blocks whose
ref starts with `stdlib:`.

Rows, in spec order: trig, inverse trig, hyperbolic, exp/log/sqrt, abs/sign, min/max/clamp,
floor/ceil/round, mod/rem, hypot, dot/norm/cross, transpose, ddt, int, deadzone/saturate,
previous, hold, reinit (the operator table's reset), then the D12 intrinsics (`interp1`,
`interp2`, `noise_normal`, `delay`).
"""
const FUNCTION_RULES = vcat(
    BASE_FUNCTION_RULES,
    FunctionRule[
        FunctionRule(
            [r.name], r.contexts, r.min_args, r.max_args, r.lowering;
            stdlib_only = r.stdlib_only,
        ) for r in INTRINSIC_RULES
    ],
)

const FUNCTION_LOOKUP = Dict{Symbol,FunctionRule}(name => rule
                                                  for rule in FUNCTION_RULES
                                                  for name in rule.names)

"""
The function additions of the spatial-mechanics section (spec "Spatial mechanics (screw
theory)", table "Function additions"), in the same `FunctionRule` style as
[`BASE_FUNCTION_RULES`](@ref) but in their own table, exactly as the spec presents them.

They are **overloaded on the shape of the argument**, which is why a scalar whitelist row
alone cannot describe them: `exp`/`log` keep their scalar meaning from the base table and
mean the screw exponential/logarithm on a pose or twist value; `hat`/`vee`/`Ad`/`ad` take a
`Vec{3}` (planar) or `Vec{6}` (spatial) twist; `compose`/`inv` take a pose; `SE3`,
`rotation` and `translation` build and take apart a spatial pose. The quaternion helpers
are the D-MB6 pose-state operations (`PoseIntegrator3D`, J-MB8) — the spec's pose-state
section requires them, its function table does not enumerate them.

`function_rule` consults this table after [`FUNCTION_RULES`](@ref). `pose_of` and
`jacobian` are deliberately absent: they are generated per model and out of scope for M3
(plan `MULTIBOND_PLAN.md` section 12).

| function | meaning | scopes |
| --- | --- | --- |
| `hat(T)`, `vee(M)` | twist to matrix form and back | all |
| `Ad(H)` | adjoint: changes the frame of a twist | all |
| `ad(T)` | small adjoint (Lie bracket) of a twist | all |
| `exp(T)`, `log(H)` | exponential and logarithm on SE(2)/SE(3) | all |
| `compose(H1, H2)`, `inv(H)` | pose composition and inverse (`H1 * H2` needs the pose value type) | all |
| `spatial_inertia(m, Ic, c)` | the 6x6 (or planar 3x3) inertia | all |
| `SE3(R, p)`, `rotation(H)`, `translation(H)` | build and take apart poses | all |
| `quat_compose`, `quat_inv`, `quat_normalise` | quaternion algebra | all |
| `quat_exp`, `quat_log`, `quat_to_matrix`, `quat_from_rotation`, `quat_rotate` | the quaternion pose state | all |
"""
const MECH_FUNCTION_RULES = FunctionRule[
    FunctionRule([:hat], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:vee], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:Ad], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:ad], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:compose], ALL_CONTEXTS, 2, 2, :mech),
    FunctionRule([:inv], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:spatial_inertia], ALL_CONTEXTS, 2, 3, :mech),
    FunctionRule([:SE3], ALL_CONTEXTS, 0, 2, :mech),
    FunctionRule([:rotation], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:translation], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_compose], ALL_CONTEXTS, 2, 2, :mech),
    FunctionRule([:quat_inv], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_normalise], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_exp], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_log], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_to_matrix], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_from_rotation], ALL_CONTEXTS, 1, 1, :mech),
    FunctionRule([:quat_rotate], ALL_CONTEXTS, 2, 2, :mech),
]

const MECH_LOOKUP = Dict{Symbol,FunctionRule}(name => rule
                                              for rule in MECH_FUNCTION_RULES
                                              for name in rule.names)

"""    mech_function_rule(name::Symbol) -> Union{FunctionRule,Nothing}

The spatial-mechanics row for a name, or `nothing`."""
mech_function_rule(name::Symbol) = get(MECH_LOOKUP, name, nothing)

"""    function_rule(name::Symbol) -> Union{FunctionRule,Nothing}

The whitelist row for a function name, or `nothing` (which the checker reports as E002).
The built-in table is consulted first, then the spatial-mechanics additions."""
function function_rule(name::Symbol)
    rule = get(FUNCTION_LOOKUP, name, nothing)
    rule === nothing || return rule
    return get(MECH_LOOKUP, name, nothing)
end

struct SyntaxRule
    key::Symbol
    label::String
    contexts::Vector{Symbol}
    lowering::Symbol
    only_in_ifelse::Bool
end

SyntaxRule(key, label, contexts, lowering; only_in_ifelse = false) =
    SyntaxRule(key, label, Symbol[Symbol(c) for c in contexts], lowering, only_in_ifelse)

"""
The operator and statement whitelist (spec table "Operators and statements per scope").
Every row is consulted by the checker, so the table is the single place a rule lives.
"""
const SYNTAX_RULES = SyntaxRule[
    SyntaxRule(:arith, "`+ - * /` and unary `-`", ALL_CONTEXTS, :inline_ops),
    SyntaxRule(:pow_int, "`^` with an integer literal exponent", ALL_CONTEXTS, :expand_pow),
    SyntaxRule(:pow_real, "`^` with a real exponent", ALL_CONTEXTS, :pow),
    SyntaxRule(:compare, "`== != < <= > >=`", [:discrete], :compare; only_in_ifelse = true),
    SyntaxRule(:logic, "`&& || !`", [:discrete], :logic; only_in_ifelse = true),
    SyntaxRule(:equation, "`a ~ b`", [:equation], :equation),
    SyntaxRule(:assign, "`x = expr`", [:discrete], :assign),
    SyntaxRule(:opassign, "`x += expr` and similar", [:discrete], :opassign),
    SyntaxRule(:ifelse, "`ifelse(c, a, b)`", ALL_CONTEXTS, :ifelse),
    SyntaxRule(:if, "`if / elseif / else`", [:equation, :discrete], :if_equations),
    SyntaxRule(:for, "`for i in 1:N`", [:equation, :discrete], :unroll_for),
    SyntaxRule(:while, "`while`, `break`, `continue`", Symbol[], :rejected),
    SyntaxRule(:array, "array literals and indexing `v[i]`", ALL_CONTEXTS, :static_array),
    SyntaxRule(:derivative, "`ddt(x)`", [:equation], :ddt),
    SyntaxRule(:integral, "`int(x, x0)`", [:equation], :int),
    SyntaxRule(:previous, "`previous(x)`", [:discrete], :sample_previous),
    SyntaxRule(:hold, "`hold(x)`", [:discrete], :sample_hold),
    SyntaxRule(:reinit, "`reinit(x, value)`", [:events], :reset),
    SyntaxRule(:funcdef, "function definitions, closures and `do` blocks", Symbol[], :rejected),
    SyntaxRule(:macro, "macros other than the scope macros", Symbol[], :rejected),
    SyntaxRule(
        :string,
        "string literals",
        Symbol[],
        :attribute_only,
    ),
    SyntaxRule(:ternary, "the `? :` ternary operator", Symbol[], :rejected),
    SyntaxRule(:broadcast, "broadcasting with `.`", Symbol[], :rejected),
]

const SYNTAX_LOOKUP = Dict{Symbol,SyntaxRule}(rule.key => rule for rule in SYNTAX_RULES)

"""    syntax_rule(key::Symbol) -> SyntaxRule

The whitelist row for an operator/statement family. Throws `KeyError` for an unknown key,
which is a programming error, not a user error."""
syntax_rule(key::Symbol) = SYNTAX_LOOKUP[key]

"""
    syntax_allowed(key::Symbol, context::Symbol; in_ifelse = false) -> Bool

Whether an operator or statement family is allowed in a context. `in_ifelse` implements the
spec's "Inside `ifelse` only" cells for comparisons and boolean operators.
"""
function syntax_allowed(key::Symbol, context::Symbol; in_ifelse::Bool = false)
    rule = syntax_rule(key)
    # `@events` bodies are discrete code for the purposes of the operator table (D19).
    ctx = context === :events ? :discrete : context
    ctx in rule.contexts && return true
    return rule.only_in_ifelse && in_ifelse && ctx in (:equation, :default)
end

"""
    SYNTAX_DESCRIPTION(key) -> String

A human label for diagnostics, e.g. `` `while`, `break`, `continue` ``.
"""
SYNTAX_DESCRIPTION(key::Symbol) = syntax_rule(key).label

# Which syntax-table row an operator belongs to. Operators not in this table are not on the
# whitelist at all (E002): `%`, `÷`, `//`, `<<`, `>>`, `&`, `|`, `⊻`, `===`, `!==`.
const OPERATOR_RULE_KEYS = Dict{Symbol,Symbol}(
    :+ => :arith,
    :- => :arith,
    :* => :arith,
    :/ => :arith,
    Symbol("\\") => :arith,
    :^ => :pow_int,
)

"""    operator_rule_key(op::Symbol) -> Union{Symbol,Nothing}

The syntax-table row for an operator, or `nothing` when the operator is not whitelisted."""
operator_rule_key(op::Symbol) = get(OPERATOR_RULE_KEYS, op, nothing)

const COMPARISON_OPS =
    Symbol[Symbol("=="), Symbol("!="), :<, :<=, :>, :>=]

"""    is_comparison_op(op) -> Bool"""
is_comparison_op(op::Symbol) = op in COMPARISON_OPS

"""
Names that are predefined in every block (spec table: `t` is readable in all scopes, `Ts`
only in discrete scopes). The checker resolves them before declarations.
"""
const PREDEFINED_NAMES = Dict{Symbol,Vector{Symbol}}(
    :t => ALL_CONTEXTS,
    :Ts => [:discrete],
)
