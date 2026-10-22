# The unit-string parser (plan 5.3: "The parser handles `*`, `/`, `^` with integer
# exponents, and parentheses.").
#
# Grammar, with `^` binding tighter than `*` and `/`, and `*`/`/` evaluated left to right:
#
#     unit      := product
#     product   := factor (('*' | '·' | whitespace) factor | '/' factor)*
#     factor    := base ('^' ('+' | '-')? integer)?
#     base      := number | name | '(' unit ')'
#
# A number is a *scale* (so `0.001*m` is `mm` and `1e5*Pa` is `bar`); it is accepted at the
# start of the unit or after an explicit operator, never as an implicit factor, so `m2` is
# an error with the hint "write `m^2`". Whitespace and `·`/`⋅`/`×` are multiplication
# separators. Names are case-sensitive (`V` is the volt, `v` is an error that suggests
# `V`); `Ω` aliases `Ohm` and `°` aliases `deg`.
#
# This is the inverse of `unit_string` in the sense that
# `parse_unit(unit_string(d)) == d` for every `d`.

"""    UnitParseError(unit, position, reason)

Raised by [`parse_unit`](@ref) for a malformed or unknown unit. `position` is a 1-based
character index into `unit`; the message is the user-facing reason without any prefix
(`check_units` turns it into an E006 that points at the declaration)."""
struct UnitParseError <: Exception
    unit::String
    position::Int
    reason::String
end

function Base.showerror(io::IO, e::UnitParseError)
    print(io, "invalid unit \"", e.unit, "\" at character ", e.position, ": ", e.reason)
    return nothing
end

# ---------------------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------------------

struct UnitToken
    kind::Symbol      # :name, :number, :mul, :div, :pow, :lparen, :rparen, :plus, :minus
    text::String
    value::Float64    # only for :number
    start::Int        # character index of the first character
    stop::Int         # character index of the last character
end

_is_unit_space(c::Char) = c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\u00a0'

function _tokenize(unit::AbstractString)
    chars = collect(unit)
    toks = UnitToken[]
    i = 1
    n = length(chars)
    while i <= n
        c = chars[i]
        if _is_unit_space(c)
            i += 1
        elseif c == '*'
            push!(toks, UnitToken(:mul, "*", 0.0, i, i))
            i += 1
        elseif c == '·' || c == '⋅' || c == '×'
            push!(toks, UnitToken(:mul, string(c), 0.0, i, i))
            i += 1
        elseif c == '/'
            push!(toks, UnitToken(:div, "/", 0.0, i, i))
            i += 1
        elseif c == '^'
            push!(toks, UnitToken(:pow, "^", 0.0, i, i))
            i += 1
        elseif c == '('
            push!(toks, UnitToken(:lparen, "(", 0.0, i, i))
            i += 1
        elseif c == ')'
            push!(toks, UnitToken(:rparen, ")", 0.0, i, i))
            i += 1
        elseif c == '+'
            push!(toks, UnitToken(:plus, "+", 0.0, i, i))
            i += 1
        elseif c == '-'
            push!(toks, UnitToken(:minus, "-", 0.0, i, i))
            i += 1
        elseif isdigit(c) || (c == '.' && i < n && isdigit(chars[i + 1]))
            j = i
            while j <= n && isdigit(chars[j])
                j += 1
            end
            if j <= n && chars[j] == '.'
                j += 1
                while j <= n && isdigit(chars[j])
                    j += 1
                end
            end
            if j <= n && (chars[j] == 'e' || chars[j] == 'E')
                k = j + 1
                if k <= n && (chars[k] == '+' || chars[k] == '-')
                    k += 1
                end
                if k <= n && isdigit(chars[k])
                    j = k
                    while j <= n && isdigit(chars[j])
                        j += 1
                    end
                end
            end
            text = String(chars[i:(j - 1)])
            value = tryparse(Float64, text)
            value === nothing &&
                throw(UnitParseError(unit, i, "`$text` is not a number"))
            push!(toks, UnitToken(:number, text, value, i, j - 1))
            i = j
        elseif isletter(c) || c == '_' || c == '°'
            j = i + 1
            while j <= n && (isletter(chars[j]) || isdigit(chars[j]) || chars[j] == '_')
                j += 1
            end
            push!(toks, UnitToken(:name, String(chars[i:(j - 1)]), 0.0, i, j - 1))
            i = j
        else
            throw(UnitParseError(unit, i, "unexpected character `$c`"))
        end
    end
    return toks
end

# ---------------------------------------------------------------------------------------
# Recursive descent
# ---------------------------------------------------------------------------------------

mutable struct _ParseState
    unit::String
    tokens::Vector{UnitToken}
    nchars::Int
    i::Int
end

_peek(p::_ParseState) = p.i <= length(p.tokens) ? p.tokens[p.i] : nothing

function _advance!(p::_ParseState)
    t = _peek(p)
    t === nothing || (p.i += 1)
    return t
end

_end_position(p::_ParseState) = max(p.nchars, 1)

function _parse_product!(p::_ParseState)::Dims
    result = _parse_factor!(p)
    while true
        t = _peek(p)
        t === nothing && break
        if t.kind === :mul
            _advance!(p)
            result = result * _parse_factor!(p)
        elseif t.kind === :div
            _advance!(p)
            result = result / _parse_factor!(p)
        elseif t.kind === :name || t.kind === :lparen
            # Implicit multiplication: `N m`, `kg m^2`, `(m)(s)`.
            result = result * _parse_factor!(p)
        else
            break
        end
    end
    return result
end

function _parse_factor!(p::_ParseState)::Dims
    t = _advance!(p)
    if t === nothing
        throw(UnitParseError(p.unit, _end_position(p), "a factor is expected here"))
    end
    base = if t.kind === :number
        t.value > 0 ||
            throw(UnitParseError(p.unit, t.start, "a unit scale must be positive, got `$(t.text)`"))
        Dims(DIMENSIONLESS.exps, t.value)
    elseif t.kind === :name
        unit = get(UNIT_TABLE, t.text, nothing)
        unit === nothing && throw(_unknown_unit(p.unit, t))
        unit
    elseif t.kind === :lparen
        inner = _parse_product!(p)
        close = _advance!(p)
        (close !== nothing && close.kind === :rparen) ||
            throw(UnitParseError(p.unit, t.start, "missing `)`"))
        inner
    else
        throw(UnitParseError(p.unit, t.start, "a unit name, a number or `(` is expected, found `$(t.text)`"))
    end
    pwr = _peek(p)
    if pwr !== nothing && pwr.kind === :pow
        _advance!(p)
        base = base^_parse_exponent!(p)
    end
    return base
end

function _parse_exponent!(p::_ParseState)::Int
    t = _advance!(p)
    t === nothing &&
        throw(UnitParseError(p.unit, _end_position(p), "an integer exponent is expected after `^`"))
    sign = 1
    if t.kind === :plus || t.kind === :minus
        sign = t.kind === :minus ? -1 : 1
        t = _advance!(p)
        t === nothing &&
            throw(UnitParseError(p.unit, _end_position(p), "an integer exponent is expected after `^`"))
    end
    if t.kind !== :number || !isinteger(t.value)
        throw(
            UnitParseError(
                p.unit,
                t.start,
                "the exponent must be an integer literal, found `$(t.text)`",
            ),
        )
    elseif abs(t.value) > 1e6
        throw(UnitParseError(p.unit, t.start, "the exponent `$(t.text)` is too large"))
    end
    return sign * Int(t.value)
end

function _unknown_unit(unit::String, t::UnitToken)
    power = match(r"^([A-Za-z_]+)([0-9]+)$", t.text)
    if power !== nothing && haskey(UNIT_TABLE, power.captures[1])
        return UnitParseError(
            unit,
            t.start,
            "unknown unit `$(t.text)`; write `$(power.captures[1])^$(power.captures[2])` for a power",
        )
    end
    matches = sort(String[
        key for key in keys(UNIT_TABLE) if
        lowercase(key) == lowercase(t.text) && key != t.text
    ])
    reason = "unknown unit `$(t.text)`"
    isempty(matches) || (reason *= "; did you mean `$(matches[1])`?")
    return UnitParseError(unit, t.start, reason)
end

# ---------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------

"""    parse_unit(s::AbstractString) -> Dims

Parse a unit string: SI base units, the derived and scaled units of plan 5.3, the
pseudo-dimensions `effort` and `flow`, `*`, `/`, `^` with an integer exponent, parentheses,
numeric scale factors and whitespace or `·` as multiplication separators.

Throws [`UnitParseError`](@ref) with a character position for anything else. The result is
a [`Dims`](@ref): exponents plus scale, so `parse_unit("mm")` is the metre dimension with
scale 0.001 and `parse_unit("rpm")` is `1/s` with scale 2π/60.

```julia
julia> parse_unit("N*m/rad")
J              # the joule dimension: m^2*kg/s^2, scale 1.0

julia> parse_unit("0.001*m/s")
0.001*m/s
```
"""
function parse_unit(s::AbstractString)::Dims
    unit = String(s)
    toks = _tokenize(unit)
    isempty(toks) && throw(UnitParseError(unit, 1, "the unit is empty"))
    p = _ParseState(unit, toks, length(collect(unit)), 1)
    d = _parse_product!(p)
    leftover = _peek(p)
    if leftover !== nothing
        reason = if leftover.kind === :number
            "unexpected number `$(leftover.text)`; write `^$(leftover.text)` for a power"
        else
            "unexpected `$(leftover.text)` after a complete unit"
        end
        throw(UnitParseError(unit, leftover.start, reason))
    end
    if !isfinite(d.scale) || d.scale <= 0
        throw(UnitParseError(unit, 1, "the unit scale is not a finite positive number"))
    end
    return d
end
