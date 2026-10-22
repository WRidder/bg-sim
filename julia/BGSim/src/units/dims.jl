# Dimensions and the named unit table (plan section 5.3, decisions D2 and D9).
#
# A `Dims` is an integer exponent vector over the seven SI base dimensions
# (m, kg, s, A, K, mol, cd) plus the two bond-graph pseudo-dimensions `effort` and `flow`
# (decision D9) and a `Float64` scale. The scale is a *unit* scale, not a value: `mm` is
# `m` with scale 1e-3, `rpm` is `1/s` with scale 2π/60, `deg` is dimensionless with scale
# π/180. Values never change the scale; only unit strings and `conversion_factor` do.
#
# Derived units are built from the base ones here, so there is exactly one definition per
# unit. `UNIT_TABLE` is what `parse_unit` accepts and `DISPLAY_UNITS` is what
# `unit_string` prefers; both live in this file so a new unit is one row.
#
# Display is dimension-based, not symbol-based: dimensionally equal units share a
# canonical spelling (`N*m` prints `J`, because a dimension checker cannot tell torque
# from energy). Diagnostics therefore prefer the unit text a declaration was written with
# (`unitcheck.jl`), and fall back to `unit_string` for computed units.

"""    Dims(exps, scale)

A dimension: nine integer exponents (m, kg, s, A, K, mol, cd, effort, flow) and a positive
`Float64` scale. Build the common ones with the keyword form:

```julia
Dims(m = 1, s = -2)              # m/s^2, scale 1
Dims(kg = 1, scale = 1e-3)       # g
parse_unit("rad/s")              # s^-1 (rad is dimensionless)
```

`*`, `/`, `^` (integer) compose dimensions; `==` compares exponents and scale exactly;
`isapprox` allows a relative tolerance on the scale so that factors computed through
different product orders compare equal. `show` prints [`unit_string`](@ref).
"""
struct Dims
    exps::NTuple{9,Int}
    scale::Float64
end

const N_DIMENSIONS = 9

"""The SI base dimension names, in exponent order (positions 1 to 7)."""
const SI_BASE_NAMES = (:m, :kg, :s, :A, :K, :mol, :cd)

"""The bond-graph pseudo-dimensions (decision D9), at positions 8 and 9."""
const PSEUDO_DIMENSION_NAMES = (:effort, :flow)

"""All nine dimension names, in exponent order."""
const DIMENSION_NAMES = (SI_BASE_NAMES..., PSEUDO_DIMENSION_NAMES...)

"""Display order of the factors in [`unit_string`](@ref): the bond-graph pseudo-dimensions
first (so `flow*s/effort` reads naturally), then the SI base dimensions."""
const DISPLAY_ORDER = (:effort, :flow, :m, :kg, :s, :A, :K, :mol, :cd)

"""The exponent position of each name in [`DISPLAY_ORDER`](@ref)."""
const DISPLAY_INDEX = (8, 9, 1, 2, 3, 4, 5, 6, 7)

Dims(exps::NTuple{9,Int}) = Dims(exps, 1.0)

"""    Dims(; m, kg, s, A, K, mol, cd, effort, flow, scale = 1.0)

The keyword constructor. Every exponent defaults to 0, so `Dims()` is dimensionless with
scale 1."""
function Dims(;
    m = 0,
    kg = 0,
    s = 0,
    A = 0,
    K = 0,
    mol = 0,
    cd = 0,
    effort = 0,
    flow = 0,
    scale = 1.0,
)
    exps = (
        Int(m), Int(kg), Int(s), Int(A), Int(K), Int(mol), Int(cd), Int(effort),
        Int(flow),
    )
    return Dims(exps, Float64(scale))
end

"""    exponents(d::Dims) -> NTuple{9,Int}

The nine integer exponents, in [`DIMENSION_NAMES`](@ref) order."""
exponents(d::Dims) = d.exps

"""    scale_of(d::Dims) -> Float64

The unit scale (`1.0` for SI, `0.001` for `mm`, `2π/60` for `rpm`)."""
scale_of(d::Dims) = d.scale

"""    exponent(d::Dims, name::Symbol) -> Int

The exponent of one dimension, e.g. `exponent(parse_unit("m/s^2"), :s) == -2`."""
function exponent(d::Dims, name::Symbol)
    i = findfirst(==(name), DIMENSION_NAMES)
    i === nothing && throw(ArgumentError("`$name` is not a dimension name"))
    return d.exps[i]
end

"""    is_dimensionless(d::Dims) -> Bool

True when all nine exponents are zero. The scale is deliberately ignored: a value declared
in `deg` or `rad` is dimensionless for the purpose of a function argument, because the
`unit` attribute does not convert the stored number (plan 5.3: "no runtime conversion")."""
is_dimensionless(d::Dims) = all(iszero, d.exps)

"""    has_pseudo_dimensions(d::Dims) -> Bool

True when `effort` or `flow` survives in `d` — i.e. the block's domain has not been
adopted yet (decision D9)."""
has_pseudo_dimensions(d::Dims) = d.exps[8] != 0 || d.exps[9] != 0

"""    with_scale(d::Dims, s::Real) -> Dims

The same exponents with the scale multiplied by `s`. `with_scale(parse_unit("m"), 0.001)`
is `mm`."""
with_scale(d::Dims, s::Real) = Dims(d.exps, d.scale * Float64(s))

Base.:*(a::Dims, b::Dims) = Dims(a.exps .+ b.exps, a.scale * b.scale)
Base.:/(a::Dims, b::Dims) = Dims(a.exps .- b.exps, a.scale / b.scale)

"""    ^(d::Dims, n::Integer) -> Dims

Raise a dimension to an integer power: exponents are multiplied and the scale is raised to
the same power. A negative power is legal; `-0` exponents stay `0`."""
function Base.:^(d::Dims, n::Integer)
    p = Int(n)
    return Dims(ntuple(i -> d.exps[i] * p, N_DIMENSIONS), d.scale^p)
end

# `x^-1` is lowered to `inv(x)` by `Base.literal_pow`, so define it explicitly.
Base.inv(d::Dims) =
    Dims(ntuple(i -> -d.exps[i], N_DIMENSIONS), 1.0 / d.scale)

function Base.:(==)(a::Dims, b::Dims)
    return a.exps == b.exps && a.scale == b.scale
end

function Base.isequal(a::Dims, b::Dims)
    return isequal(a.exps, b.exps) && isequal(a.scale, b.scale)
end

function Base.isapprox(a::Dims, b::Dims; rtol::Real = 1e-12, atol::Real = 0.0, nans::Bool = false)
    a.exps == b.exps || return false
    return isapprox(a.scale, b.scale; rtol = rtol, atol = atol, nans = nans)
end

function Base.hash(d::Dims, h::UInt)
    return hash(d.scale, hash(d.exps, hash(:BGSimDims, h)))
end

Base.show(io::IO, d::Dims) = print(io, unit_string(d))

# ---------------------------------------------------------------------------------------
# The named units
# ---------------------------------------------------------------------------------------

const UNIT_M = Dims(m = 1)
const UNIT_KG = Dims(kg = 1)
const UNIT_S = Dims(s = 1)
const UNIT_A = Dims(A = 1)
const UNIT_K = Dims(K = 1)
const UNIT_MOL = Dims(mol = 1)
const UNIT_CD = Dims(cd = 1)
const UNIT_EFFORT = Dims(effort = 1)
const UNIT_FLOW = Dims(flow = 1)

"""The dimensionless dimension with scale 1: what `parse_unit("1")` returns."""
const DIMENSIONLESS = Dims()

const UNIT_N = UNIT_M * UNIT_KG / UNIT_S^2
const UNIT_J = UNIT_N * UNIT_M
const UNIT_W = UNIT_J / UNIT_S
const UNIT_V = UNIT_W / UNIT_A
const UNIT_OHM = UNIT_V / UNIT_A
const UNIT_F = UNIT_A * UNIT_S / UNIT_V
const UNIT_H = UNIT_V * UNIT_S / UNIT_A
const UNIT_PA = UNIT_N / UNIT_M^2
const UNIT_HZ = Dims(s = -1)

"""    UNIT_TABLE -> Dict{String,Dims}

Every unit string [`parse_unit`](@ref) accepts: the seven SI base units, the derived units
of plan 5.3 (N, J, W, V, Ohm, F, H, Pa, bar, Hz, rpm, rad, deg) and the scaled ones
(mm, cm, g, min, h, L), plus the pseudo-dimensions `effort` and `flow`.

`rad` is dimensionless (scale 1); `rpm` is `1/s` with scale 2π/60 (the `rad` dimension is
dropped, as plan 5.3 says); `deg` is dimensionless with scale π/180. `Ω` is an alias of
`Ohm` and `°` of `deg`.
"""
const UNIT_TABLE = Dict{String,Dims}(
    "1" => DIMENSIONLESS,
    "m" => UNIT_M,
    "kg" => UNIT_KG,
    "s" => UNIT_S,
    "A" => UNIT_A,
    "K" => UNIT_K,
    "mol" => UNIT_MOL,
    "cd" => UNIT_CD,
    "g" => with_scale(UNIT_KG, 1e-3),
    "mm" => with_scale(UNIT_M, 1e-3),
    "cm" => with_scale(UNIT_M, 1e-2),
    "min" => with_scale(UNIT_S, 60.0),
    "h" => with_scale(UNIT_S, 3600.0),
    "N" => UNIT_N,
    "J" => UNIT_J,
    "W" => UNIT_W,
    "V" => UNIT_V,
    "Ohm" => UNIT_OHM,
    "Ω" => UNIT_OHM,
    "F" => UNIT_F,
    "H" => UNIT_H,
    "Pa" => UNIT_PA,
    "bar" => with_scale(UNIT_PA, 1e5),
    "Hz" => UNIT_HZ,
    "rpm" => with_scale(UNIT_HZ, 2π / 60),
    "rad" => DIMENSIONLESS,
    "deg" => with_scale(DIMENSIONLESS, π / 180),
    "°" => with_scale(DIMENSIONLESS, π / 180),
    "L" => with_scale(UNIT_M^3, 1e-3),
    "effort" => UNIT_EFFORT,
    "flow" => UNIT_FLOW,
)

"""Preferred spellings for [`unit_string`](@ref), most specific first. Only exact matches
(exponents *and* scale) are used, so this table cannot change a dimension; it only picks a
name for one. `rad` and `Hz` are deliberately absent: both are dimensionally the same as
`1` and `1/s`, and a dimension checker must not claim a frequency is an angular velocity."""
const DISPLAY_UNITS = Tuple{String,Dims}[
    ("mm", with_scale(UNIT_M, 1e-3)),
    ("cm", with_scale(UNIT_M, 1e-2)),
    ("g", with_scale(UNIT_KG, 1e-3)),
    ("min", with_scale(UNIT_S, 60.0)),
    ("h", with_scale(UNIT_S, 3600.0)),
    ("L", with_scale(UNIT_M^3, 1e-3)),
    ("bar", with_scale(UNIT_PA, 1e5)),
    ("rpm", with_scale(UNIT_HZ, 2π / 60)),
    ("deg", with_scale(DIMENSIONLESS, π / 180)),
    ("N", UNIT_N),
    ("J", UNIT_J),
    ("W", UNIT_W),
    ("V", UNIT_V),
    ("Ohm", UNIT_OHM),
    ("F", UNIT_F),
    ("H", UNIT_H),
    ("Pa", UNIT_PA),
    ("m", UNIT_M),
    ("kg", UNIT_KG),
    ("s", UNIT_S),
    ("A", UNIT_A),
    ("K", UNIT_K),
    ("mol", UNIT_MOL),
    ("cd", UNIT_CD),
    ("effort", UNIT_EFFORT),
    ("flow", UNIT_FLOW),
]

"""    unit_string(d::Dims) -> String

The canonical unit string for `d`, in a form `parse_unit` accepts again:

* an exact named unit when one matches (`"N"`, `"mm"`, `"rpm"`, `"deg"`, ...);
* otherwise the base expansion with the pseudo-dimensions first
  (`"m/s"`, `"flow*s/effort"`, `"m^2*kg/s^2"`);
* a scale prefix when the scale is not 1 (`"0.001*m/s"`), and the bare scale for a
  scaled dimensionless dimension (`"60"`).

Dimensionally equal units share one spelling, so `unit_string(parse_unit("N*m")) == "J"`.
Round-tripping is therefore `parse_unit(unit_string(d)) == d`, not a textual identity.
"""
function unit_string(d::Dims)::String
    for (name, unit) in DISPLAY_UNITS
        d == unit && return name
    end
    num = String[]
    den = String[]
    for (i, name) in enumerate(DISPLAY_ORDER)
        e = d.exps[DISPLAY_INDEX[i]]
        e == 0 && continue
        push!(e > 0 ? num : den, _power_string(String(name), abs(e)))
    end
    if isempty(num) && isempty(den)
        return d.scale == 1.0 ? "1" : string(d.scale)
    end
    body = isempty(num) ? "1" : join(num, "*")
    if !isempty(den)
        body *= "/" * (length(den) == 1 ? den[1] : "(" * join(den, "*") * ")")
    end
    d.scale == 1.0 && return body
    return string(d.scale) * "*" * body
end

_power_string(name::String, e::Int) = e == 1 ? name : name * "^" * string(e)

"""    conversion_factor(from::Dims, to::Dims) -> Union{Float64,Nothing}

The factor that converts a value written in `from` into `to`: `from.scale / to.scale`
when the exponents agree, `nothing` when the dimensions differ (plan 5.3: "the same
dimension with a different scale inserts a factor, returned as `unitFactors` for the
editor badge"). `conversion_factor(mm, m)` is 0.001; `conversion_factor(rpm, rad/s)` is
2π/60. String arguments are parsed when needed.

The connection-level E102 (different dimensions on a wire) is J2.5; this function is the
API that WP uses.
"""
function conversion_factor(from::Dims, to::Dims)::Union{Float64,Nothing}
    from.exps == to.exps || return nothing
    return from.scale / to.scale
end

function conversion_factor(from::AbstractString, to::AbstractString)::Union{Float64,Nothing}
    return conversion_factor(parse_unit(from), parse_unit(to))
end

# ---------------------------------------------------------------------------------------
# Domains (decision D8 and D9)
# ---------------------------------------------------------------------------------------

"""    DOMAIN_EFFORT, DOMAIN_FLOW -> Dict{Symbol,Dims}

The concrete effort and flow dimension of every power domain (decision D8). `Generic`
keeps the symbolic pseudo-dimensions; `Planar` and `Spatial` are per-axis translations
(force and velocity), which is what M4 builds on.

| domain | effort | flow |
| --- | --- | --- |
| Electrical | V | A |
| Translation | N | m/s |
| Rotation | N·m | rad/s |
| Hydraulic | Pa | m³/s |
| Planar, Spatial | N | m/s |
| Generic | effort | flow |
"""
const DOMAIN_EFFORT = Dict{Symbol,Dims}(
    :Generic => UNIT_EFFORT,
    :Electrical => UNIT_V,
    :Translation => UNIT_N,
    :Rotation => UNIT_N * UNIT_M,
    :Hydraulic => UNIT_PA,
    :Planar => UNIT_N,
    :Spatial => UNIT_N,
)

const DOMAIN_FLOW = Dict{Symbol,Dims}(
    :Generic => UNIT_FLOW,
    :Electrical => UNIT_A,
    :Translation => UNIT_M / UNIT_S,
    :Rotation => UNIT_HZ,
    :Hydraulic => UNIT_M^3 / UNIT_S,
    :Planar => UNIT_M / UNIT_S,
    :Spatial => UNIT_M / UNIT_S,
)

"""The spellings used for port fields in diagnostics, per domain."""
const DOMAIN_UNIT_LABELS = Dict{Symbol,NTuple{2,String}}(
    :Generic => ("effort", "flow"),
    :Electrical => ("V", "A"),
    :Translation => ("N", "m/s"),
    :Rotation => ("N*m", "rad/s"),
    :Hydraulic => ("Pa", "m^3/s"),
    :Planar => ("N", "m/s"),
    :Spatial => ("N", "m/s"),
)

"""    effort_dims(domain::Symbol) -> Dims

The effort dimension of a power domain. An unknown domain symbol falls back to the
`Generic` pseudo-dimension so that a block with a mistyped domain cannot crash the fast
check (J1.1 owns the domain names)."""
effort_dims(domain::Symbol) = get(DOMAIN_EFFORT, domain, UNIT_EFFORT)

"""    flow_dims(domain::Symbol) -> Dims

The flow dimension of a power domain; same fallback as [`effort_dims`](@ref)."""
flow_dims(domain::Symbol) = get(DOMAIN_FLOW, domain, UNIT_FLOW)

"""    substitute_domain(d::Dims, domain::Symbol) -> Dims

Replace the pseudo-dimensions `effort` and `flow` by the concrete effort and flow of
`domain` (decision D9): `flow*s/effort` becomes `F` for `Electrical`, `m/N` for
`Translation` and `rad/(N*m)` for `Rotation`. The exponents of the replacements are added
to the SI part and their scales multiply the result; the pseudo slots are then zero.

`Generic` returns `d` unchanged (nothing has been adopted yet). An unknown domain throws
`ArgumentError`: that is a programming error in a caller, not user input.
"""
function substitute_domain(d::Dims, domain::Symbol)::Dims
    domain === :Generic && return d
    if !haskey(DOMAIN_EFFORT, domain) || !haskey(DOMAIN_FLOW, domain)
        throw(ArgumentError("unknown domain `$domain`; expected :Electrical, :Translation, :Rotation, :Hydraulic, :Planar, :Spatial or :Generic"))
    end
    ee = d.exps[8]
    fe = d.exps[9]
    (ee == 0 && fe == 0) && return d
    e = DOMAIN_EFFORT[domain]
    f = DOMAIN_FLOW[domain]
    si = ntuple(i -> d.exps[i] + ee * e.exps[i] + fe * f.exps[i], 7)
    scale = d.scale * e.scale^ee * f.scale^fe
    return Dims((si..., 0, 0), scale)
end
