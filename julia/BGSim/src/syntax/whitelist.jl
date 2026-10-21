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
The built-in function whitelist (spec table "Built-in function whitelist"), including the
D12 intrinsics. `stdlib_only` restricts a call to blocks whose ref starts with `stdlib:`.

Rows, in spec order: trig, inverse trig, hyperbolic, exp/log/sqrt, abs/sign, min/max/clamp,
floor/ceil/round, mod/rem, hypot, dot/norm/cross, transpose, ddt, int, deadzone/saturate,
delay, previous, hold, then the D12 intrinsics and `reinit`.
"""
const FUNCTION_RULES = FunctionRule[
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
    FunctionRule([:delay], [:equation], 2, 2, :delay; stdlib_only = true),
    FunctionRule([:previous], [:discrete], 1, 1, :sample_previous),
    FunctionRule([:hold], [:discrete], 1, 1, :sample_hold),
    FunctionRule([:interp1], ALL_CONTEXTS, 3, 3, :intrinsic),
    FunctionRule([:interp2], ALL_CONTEXTS, 4, 4, :intrinsic),
    FunctionRule([:noise_normal], [:discrete], 2, 2, :intrinsic; stdlib_only = true),
    FunctionRule([:reinit], [:events], 2, 2, :reset),
]

const FUNCTION_LOOKUP = Dict{Symbol,FunctionRule}(name => rule
                                                  for rule in FUNCTION_RULES
                                                  for name in rule.names)

"""    function_rule(name::Symbol) -> Union{FunctionRule,Nothing}

The whitelist row for a function name, or `nothing` (which the checker reports as E002)."""
function_rule(name::Symbol) = get(FUNCTION_LOOKUP, name, nothing)

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
    context in rule.contexts && return true
    return rule.only_in_ifelse && in_ifelse && context in (:equation, :default)
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
