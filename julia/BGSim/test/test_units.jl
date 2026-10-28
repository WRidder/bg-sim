# J1.2 — units: the parser, the dimension arithmetic, the domain substitution and the
# block-level check (plan 5.3, decisions D2 and D9).
#
# The suite covers the acceptance list of the work package: 30+ unit strings parsed and
# round-tripped, the mm→m and rpm→rad/s scale factors, the `flow*s/effort` substitution for
# Electrical/Translation/Rotation, and 15+ E006 cases asserting the exact line and column
# of the offending term. The 36 catalog blocks are parsed and checked too: they are the
# regression net for false positives, because every one of them is valid SI.
using Test
using JSON3
import BGSim
using BGSim:
    parse_block,
    check_block,
    block_equations,
    block_name,
    block_ref,
    source_range,
    decl_range,
    decl_name,
    declarations,
    equations,
    expr_range,
    Diagnostic,
    SourceRange,
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
    BoolOp

const Units = BGSim.Units
const Dims = Units.Dims

const ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const CATALOG_FIXTURE =
    joinpath(ROOT, "contracts", "fixtures", "catalog", "valid", "catalog.min.json")

const M = Units.parse_unit("m")
const S = Units.parse_unit("s")
const KG = Units.parse_unit("kg")
const N = Units.parse_unit("N")
const V = Units.parse_unit("V")
const A = Units.parse_unit("A")

test_range() = SourceRange(1, 1, 1, 1)

"""The (line, col) of a diagnostic, or `nothing`."""
function unit_at(d::Diagnostic)
    d.source === nothing && return nothing
    r = d.source.range
    r === nothing && return nothing
    return (r.line, r.col)
end

"""Every E006 diagnostic of a block, in check order."""
unit_diags(pb) = [d for d in check_block(pb) if d.code == "E006"]
unit_codes(pb) = [d.code for d in unit_diags(pb)]

"""Assert that exactly one unit diagnostic exists, with `code` at exactly `(line, col)`,
containing `contains`. Returns it."""
function expect_unit(pb, code::String, line::Int, col::Int; contains = nothing)
    hits = [
        d for d in unit_diags(pb) if
        d.code == code && (contains === nothing || occursin(contains, d.message))
    ]
    @test !isempty(hits)
    isempty(hits) && return nothing
    @test unit_at(hits[1]) == (line, col)
    return hits[1]
end

function parse_error(text)
    try
        Units.parse_unit(text)
        return nothing
    catch err
        err isa Units.UnitParseError || rethrow()
        return err
    end
end

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J1.2 units" begin
    # -----------------------------------------------------------------------------------
    @testset "Dims: dimensions, scale and arithmetic" begin
        d = Dims(m = 1, s = -2)
        @test d isa Dims
        @test Units.exponents(d) == (1, 0, -2, 0, 0, 0, 0, 0, 0)
        @test Units.exponent(d, :m) == 1
        @test Units.exponent(d, :s) == -2
        @test Units.exponent(d, :kg) == 0
        @test Units.scale_of(d) == 1.0
        @test_throws ArgumentError Units.exponent(d, :furlong)

        @test Dims() == Units.DIMENSIONLESS
        @test Units.is_dimensionless(Dims())
        @test !Units.is_dimensionless(d)
        @test Units.has_pseudo_dimensions(Dims(flow = 1))
        @test !Units.has_pseudo_dimensions(d)
        @test Units.with_scale(M, 0.001) == Units.parse_unit("mm")

        # `*`, `/` and `^` compose dimensions and scales (plan 5.3).
        @test M * S == Dims(m = 1, s = 1)
        @test M / S == Dims(m = 1, s = -1)
        @test (M / S)^2 == Dims(m = 2, s = -2)
        @test M^0 == Units.DIMENSIONLESS
        @test M^-1 == Dims(m = -1)
        @test Units.parse_unit("N") == KG * M / S^2
        @test Units.parse_unit("J") == Units.parse_unit("N*m")
        @test Units.parse_unit("W") == Units.parse_unit("J/s")
        @test Units.parse_unit("V") == Units.parse_unit("W/A")
        @test Units.parse_unit("Ohm") == Units.parse_unit("V/A")
        @test Units.parse_unit("F") == Units.parse_unit("A*s/V")
        @test Units.parse_unit("H") == Units.parse_unit("V*s/A")
        @test Units.parse_unit("Pa") == Units.parse_unit("N/m^2")
        @test Units.parse_unit("Hz") == Units.parse_unit("1/s")

        # Equality, hashing and approximate equality are consistent.
        @test Units.parse_unit("mm") == Units.parse_unit("0.001*m")
        @test Units.parse_unit("N") != Units.parse_unit("J")
        @test isequal(Units.parse_unit("N"), Units.parse_unit("kg*m/s^2"))
        @test hash(Units.parse_unit("N")) == hash(Units.parse_unit("kg*m/s^2"))
        @test length(Set([Units.parse_unit("N"), Units.parse_unit("kg*m/s^2")])) == 1
        a = Units.with_scale(M, 1.0 + 1e-14)
        @test a != M
        @test isapprox(a, M)
        @test !isapprox(Units.with_scale(M, 1.01), M)

        # `show` is `unit_string`.
        @test sprint(show, Units.parse_unit("V")) == "V"
        @test sprint(show, Units.parse_unit("m/s")) == "m/s"
        @test string(Units.DIMENSIONLESS) == "1"
    end

    # -----------------------------------------------------------------------------------
    @testset "unit strings: 30+ parse and round-trip" begin
        # Every entry of the named-unit table (plan 5.3's list) round-trips: the parser
        # understands what `unit_string` prints, and printing is idempotent.
        @test length(Units.UNIT_TABLE) >= 30
        for (text, expected) in Units.UNIT_TABLE
            d = Units.parse_unit(text)
            @test d == expected
            printed = Units.unit_string(d)
            @test Units.parse_unit(printed) == d
            @test Units.unit_string(Units.parse_unit(printed)) == printed
        end

        # Composed strings, including every spelling the spec and the stdlib use.
        composed = [
            "m/s", "m/s^2", "m^2", "m^3", "1/s", "kg*m^2", "kg*m^2/s^2", "N*m",
            "N*m/rad", "N*m*s/rad", "N*m/A", "N*s/m", "N/m", "V/A", "A*s/V", "W/A",
            "J/s", "Pa*s", "m^3/s", "effort", "flow", "effort*s", "flow*s",
            "flow*s/effort", "effort*s/flow", "effort/flow", "effort/flow*s",
            "0.001*m/s", "60*s", "m/(s^2*kg)", "(m/s)^2", "s^-2", "m^0",
        ]
        @test length(composed) >= 30
        for text in composed
            d = Units.parse_unit(text)
            printed = Units.unit_string(d)
            @test Units.parse_unit(printed) == d
            @test Units.unit_string(Units.parse_unit(printed)) == printed
        end

        # 30+ distinct unit strings with a hard-coded expected canonical spelling. The
        # canonical form is dimension-based, so dimensionally equal units share a name
        # (`N*m` prints `J`); this is documented on `unit_string`.
        canonical = [
            "m" => "m",
            "kg" => "kg",
            "s" => "s",
            "A" => "A",
            "K" => "K",
            "mol" => "mol",
            "cd" => "cd",
            "N" => "N",
            "J" => "J",
            "W" => "W",
            "V" => "V",
            "Ohm" => "Ohm",
            "F" => "F",
            "H" => "H",
            "Pa" => "Pa",
            "bar" => "bar",
            "Hz" => "1/s",
            "rpm" => "rpm",
            "rad" => "1",
            "deg" => "deg",
            "mm" => "mm",
            "cm" => "cm",
            "g" => "g",
            "min" => "min",
            "h" => "h",
            "L" => "L",
            "m/s" => "m/s",
            "m/s^2" => "m/s^2",
            "m^3/s" => "m^3/s",
            "kg*m^2" => "m^2*kg",
            "N*m" => "J",
            "N*m/rad" => "J",
            "N*m*s/rad" => "m^2*kg/s",
            "N*s/m" => "kg/s",
            "N/m" => "kg/s^2",
            "effort" => "effort",
            "flow" => "flow",
            "flow*s/effort" => "flow*s/effort",
            "effort*s/flow" => "effort*s/flow",
            "effort*s" => "effort*s",
            "1" => "1",
        ]
        @test length(canonical) >= 30
        for (text, expected) in canonical
            @test Units.unit_string(Units.parse_unit(text)) == expected
        end

        # The scaled units are exactly the plan 5.3 factors.
        @test Units.scale_of(Units.parse_unit("mm")) == 0.001
        @test Units.scale_of(Units.parse_unit("cm")) == 0.01
        @test Units.scale_of(Units.parse_unit("m")) == 1.0
        @test Units.scale_of(Units.parse_unit("g")) == 0.001
        @test Units.scale_of(Units.parse_unit("min")) == 60.0
        @test Units.scale_of(Units.parse_unit("h")) == 3600.0
        @test Units.scale_of(Units.parse_unit("bar")) == 1e5
        @test Units.scale_of(Units.parse_unit("L")) == 0.001
        @test Units.parse_unit("mm") == Units.with_scale(M, 1e-3)
        @test Units.parse_unit("mm/s") == Units.with_scale(M / S, 1e-3)
        @test Units.parse_unit("L") == Units.with_scale(M^3, 1e-3)
        @test Units.parse_unit("bar") == Units.with_scale(Units.parse_unit("Pa"), 1e5)
        @test Units.scale_of(Units.parse_unit("rpm")) == 2π / 60
        @test Units.parse_unit("rpm").exps == Units.parse_unit("rad/s").exps
        @test Units.scale_of(Units.parse_unit("deg")) == π / 180
        @test Units.is_dimensionless(Units.parse_unit("rad"))
        @test Units.is_dimensionless(Units.parse_unit("deg"))

        # Aliases and spellings.
        @test Units.parse_unit("Ω") == Units.parse_unit("Ohm")
        @test Units.parse_unit("°") == Units.parse_unit("deg")
        @test Units.parse_unit("N m") == Units.parse_unit("N*m")
        @test Units.parse_unit("N·m") == Units.parse_unit("N*m")
        @test Units.parse_unit("N⋅m") == Units.parse_unit("N*m")
        @test Units.parse_unit("kg m / s^2") == Units.parse_unit("N")
        @test Units.parse_unit("m/(s^2*kg)") == Units.parse_unit("m/s^2/kg")
        @test Units.parse_unit("(m/s)^2") == Units.parse_unit("m^2/s^2")
        @test Units.parse_unit("s^-2") == Units.parse_unit("1/s^2")
        @test Units.parse_unit("s^+2") == Units.parse_unit("s^2")
        @test Units.parse_unit("m^0") == Units.DIMENSIONLESS
        @test Units.parse_unit("0.001*m") == Units.parse_unit("mm")
        @test Units.scale_of(Units.parse_unit("2*s")) == 2.0
        @test Units.scale_of(Units.parse_unit("1.5e-3*m")) == 1.5e-3

        # Errors carry a character position and a useful reason.
        @test parse_error("") !== nothing
        @test occursin("empty", parse_error("").reason)
        for bad in ("m/", "(m", "m)", "furlong", "*m", "m/*s", "()", "m^-", "m^2.5", "%")
            @test parse_error(bad) !== nothing
        end
        @test occursin("did you mean `V`", parse_error("v").reason)
        @test occursin("write `m^2`", parse_error("m2").reason)
        @test occursin("integer literal", parse_error("m^2.5").reason)
        @test occursin("unknown unit", parse_error("furlong").reason)
        @test parse_error("m^2.5").position == 3
        @test parse_error("v").position == 1
        @test sprint(showerror, parse_error("furlong")) ==
              "invalid unit \"furlong\" at character 1: unknown unit `furlong`"
    end

    # -----------------------------------------------------------------------------------
    @testset "conversion factors: mm→m, rpm→rad/s, deg" begin
        # The acceptance list of the work package, exactly.
        @test Units.conversion_factor(Units.parse_unit("mm"), M) == 0.001
        @test Units.conversion_factor(Units.parse_unit("rpm"), Units.parse_unit("rad/s")) ==
              2π / 60
        @test Units.conversion_factor(Units.parse_unit("rpm"), Units.parse_unit("rad/s")) ≈
              0.10471975511965977
        @test Units.conversion_factor(Units.parse_unit("deg"), Units.DIMENSIONLESS) ==
              π / 180
        @test Units.conversion_factor(Units.parse_unit("deg"), Units.parse_unit("rad")) ==
              π / 180

        @test Units.conversion_factor("mm", "m") == 0.001
        @test Units.conversion_factor("rpm", "rad/s") == 2π / 60
        @test Units.conversion_factor("m", "mm") == 1000.0
        @test Units.conversion_factor("cm", "m") == 0.01
        @test Units.conversion_factor("g", "kg") == 0.001
        @test Units.conversion_factor("min", "s") == 60.0
        @test Units.conversion_factor("h", "s") == 3600.0
        @test Units.conversion_factor("bar", "Pa") == 1e5
        @test Units.conversion_factor("L", "m^3") == 0.001
        @test Units.conversion_factor("N", "kg*m/s^2") == 1.0
        @test Units.conversion_factor("V", "V") == 1.0

        # Different dimensions have no factor (the connection pass reports E102, J2.5).
        @test Units.conversion_factor(M, S) === nothing
        @test Units.conversion_factor("N", "m/s") === nothing
        @test Units.conversion_factor("rpm", "m") === nothing
    end

    # -----------------------------------------------------------------------------------
    @testset "pseudo-dimensions and domain substitution (D9)" begin
        c = Units.parse_unit("flow*s/effort")

        # The work package's acceptance: a capacitance on each bond.
        @test Units.substitute_domain(c, :Electrical) == Units.parse_unit("F")
        @test Units.substitute_domain(c, :Translation) == Units.parse_unit("m/N")
        @test Units.substitute_domain(c, :Rotation) ==
              Units.parse_unit("rad") / Units.parse_unit("N*m")
        @test Units.substitute_domain(c, :Hydraulic) == Units.parse_unit("m^3/Pa")
        @test Units.unit_string(Units.substitute_domain(c, :Electrical)) == "F"
        @test Units.substitute_domain(c, :Generic) == c
        @test Units.has_pseudo_dimensions(Units.substitute_domain(c, :Generic))
        @test !Units.has_pseudo_dimensions(Units.substitute_domain(c, :Electrical))

        # An inertia and a resistance.
        i = Units.parse_unit("effort*s/flow")
        @test Units.substitute_domain(i, :Electrical) == Units.parse_unit("H")
        @test Units.substitute_domain(i, :Translation) == Units.parse_unit("kg")
        @test Units.substitute_domain(i, :Rotation) == Units.parse_unit("kg*m^2")
        r = Units.parse_unit("effort/flow")
        @test Units.substitute_domain(r, :Electrical) == Units.parse_unit("Ohm")
        @test Units.substitute_domain(r, :Translation) == Units.parse_unit("N*s/m")
        @test Units.substitute_domain(r, :Rotation) == Units.parse_unit("N*m*s/rad")

        # Domain table (decision D8).
        @test Units.effort_dims(:Electrical) == V
        @test Units.flow_dims(:Electrical) == A
        @test Units.effort_dims(:Translation) == N
        @test Units.flow_dims(:Translation) == Units.parse_unit("m/s")
        @test Units.effort_dims(:Rotation) == Units.parse_unit("N*m")
        @test Units.flow_dims(:Rotation) == Units.parse_unit("rad/s")
        @test Units.effort_dims(:Hydraulic) == Units.parse_unit("Pa")
        @test Units.flow_dims(:Hydraulic) == Units.parse_unit("m^3/s")
        @test Units.effort_dims(:Generic) == Units.parse_unit("effort")
        @test Units.flow_dims(:Generic) == Units.parse_unit("flow")
        # A multibond port has no single unit: a planar component 1 is a torque, 2 and 3
        # are forces (F9/D-MB10). The whole-port form refuses instead of claiming `N`.
        @test_throws ArgumentError Units.effort_dims(:Planar)
        @test_throws ArgumentError Units.flow_dims(:Planar)
        @test_throws ArgumentError Units.effort_dims(:Spatial)
        @test_throws ArgumentError Units.flow_dims(:Spatial)
        @test Units.effort_dims(:Planar, 1) == Units.parse_unit("N*m")
        @test Units.effort_dims(:Planar, 2) == N
        @test Units.effort_dims(:Planar, 3) == N
        @test Units.flow_dims(:Planar, 1) == Units.parse_unit("rad/s")
        @test Units.flow_dims(:Planar, 2) == Units.parse_unit("m/s")
        @test Units.flow_dims(:Planar, 3) == Units.parse_unit("m/s")
        @test Units.component_count(:Planar) == 3
        @test Units.component_count(:Spatial) == 6
        @test Units.component_count(:Rotation) == 1
        @test Units.effort_component_dims(:Spatial) ==
              [Units.parse_unit("N*m"), Units.parse_unit("N*m"), Units.parse_unit("N*m"),
                  N, N, N]
        @test Units.flow_component_dims(:Planar) ==
              [Units.parse_unit("rad/s"), Units.parse_unit("m/s"), Units.parse_unit("m/s")]
        @test Units.effort_component_dims(:Rotation) == [Units.parse_unit("N*m")]
        @test Units.power_dims(:Planar) == Units.parse_unit("W")
        @test Units.power_dims(:Spatial) == Units.parse_unit("W")
        @test Units.power_dims(:Rotation) == Units.parse_unit("W")
        @test Units.power_dims(:Generic) ==
              Units.parse_unit("effort") * Units.parse_unit("flow")
        @test Units.domain_effort_unit_strings(:Planar) == ["N*m", "N", "N"]
        @test Units.domain_flow_unit_strings(:Spatial) ==
              ["rad/s", "rad/s", "rad/s", "m/s", "m/s", "m/s"]
        @test Units.domain_effort_unit_strings(:Rotation) == ["N*m"]
        @test Units.flow_dims(:UnknownDomain) == Units.parse_unit("flow")

        @test_throws ArgumentError Units.substitute_domain(c, :NoSuchDomain)
        @test_throws ArgumentError Units.substitute_domain(M, :NoSuchDomain)
        @test Units.substitute_domain(M, :Electrical) == M
    end

    # -----------------------------------------------------------------------------------
    @testset "dims_of: the pure API" begin
        r = test_range()
        env = Units.UnitEnv(
            Dict(
                :x => M,
                :v => Units.parse_unit("m/s"),
                Symbol("p.e") => V,
                Symbol("p.f") => A,
            )
        )
        @test Units.dims_of(Name(:x, r), env) == M
        @test Units.dims_of(Name(:unknown, r), env) === nothing
        @test Units.dims_of(Lit(1.0, r), env) === nothing
        @test Units.dims_of(Lit(2, r), env) === nothing
        @test Units.dims_of(Field(Name(:p, r), :e, r), env) == V
        @test Units.dims_of(Field(Name(:p, r), :f, r), env) == A
        @test Units.dims_of(Field(Name(:q, r), :e, r), env) === nothing
        @test Units.dims_of(UnOp(Symbol("-"), Name(:x, r), r), env) == M
        @test Units.dims_of(Index(Name(:x, r), BGSim.Expr[Lit(1, r)], r), env) == M

        # Multiplication and division compose; a literal is a multiplicative identity.
        @test Units.dims_of(BinOp(:*, Name(:x, r), Lit(2.0, r), r), env) == M
        @test Units.dims_of(BinOp(:*, Lit(2.0, r), Name(:v, r), r), env) ==
              Units.parse_unit("m/s")
        @test Units.dims_of(BinOp(:/, Name(:x, r), Lit(2.0, r), r), env) == M
        @test Units.dims_of(BinOp(:/, Lit(1.0, r), Name(:x, r), r), env) ==
              Units.parse_unit("1/m")
        @test Units.dims_of(BinOp(:/, Name(:x, r), Name(:v, r), r), env) ==
              Units.parse_unit("s")
        @test Units.dims_of(BinOp(:^, Name(:x, r), Lit(2, r), r), env) == M^2
        @test Units.dims_of(
            BinOp(:+, Name(:x, r), Lit(0.0, r), r),
            env,
        ) == M
        # A wildcard in a sum or a product makes the result unknown; a numeric literal
        # does not (it is a unitless zero/scale factor).
        @test Units.dims_of(BinOp(:+, Name(:x, r), Name(:unknown, r), r), env) === nothing
        @test Units.dims_of(BinOp(:*, Name(:x, r), Name(:unknown, r), r), env) === nothing
        @test Units.dims_of(BinOp(:+, Name(:x, r), Lit(0.0, r), r), env) == M

        # A plain dictionary is accepted; a `nothing` value is a wildcard.
        @test Units.dims_of(Name(:x, r), Dict(:x => M)) == M
        @test Units.dims_of(Name(:x, r), Dict(:x => nothing)) === nothing
        @test Units.dims_of(Name(:x, r)) === nothing
        @test Units.UnitEnv() isa Units.UnitEnv
        @test_throws ArgumentError Units.UnitEnv(Dict(:x => 1.0))
    end

    # -----------------------------------------------------------------------------------
    @testset "unit_env: declarations, ports and domain adoption" begin
        pb = parse_block(
            """
            @block Elec begin
                @ports p::Power{Electrical}
                @parameters r::Real = 1.0, [unit = "effort/flow"]
                @parameters v::Real = 0.0, [unit = "V"]
                @equations p.e ~ r * p.f + v
            end
            """;
            ref = "project:Elec",
        )
        @test Units.block_domain(pb) == :Electrical
        env = Units.unit_env(pb)
        @test env.names[:r] == Units.parse_unit("Ohm")   # effort/flow adopted
        @test env.labels[:r] == "effort/flow"
        @test env.names[:v] == V
        @test env.names[Symbol("p.e")] == V
        @test env.names[Symbol("p.f")] == A
        @test env.names[:t] == S
        @test env.labels[Symbol("p.e")] == "V"
        @test env.constants isa Dict{Symbol,Any}
        @test isempty(Units.check_units(pb))

        generic = parse_block(
            """
            @block Generic begin
                @ports p::Power{Generic}
                @parameters c::Real = 1.0, [unit = "flow*s/effort"]
                @variables q::Real = 0.0, [unit = "flow*s"]
                @equations begin
                    ddt(q) ~ p.f
                    p.e ~ q / c
                end
            end
            """;
            ref = "stdlib:bondgraph/C",
        )
        @test Units.block_domain(generic) == :Generic
        genv = Units.unit_env(generic)
        @test genv.names[:c] == Units.parse_unit("flow*s/effort")
        @test Units.has_pseudo_dimensions(genv.names[:c])
        @test isempty(Units.check_units(generic))

        # Constants fold into the environment and can be used as exponents/factors.
        consts = parse_block(
            """
            @block Consts begin
                @constants N::Int = 2
                @parameters a::Real = 1.0, [unit = "m"]
                @variables y::Real, [unit = "m^2"]
                @equations y ~ a ^ N
            end
            """,
        )
        @test Units.unit_env(consts).constants[:N] == 2
        @test isempty(Units.check_units(consts))
    end

    # -----------------------------------------------------------------------------------
    @testset "E006: one case per rule, exact line and column" begin
        cases = [
            (
                name = "addition",
                source = """
                @block AddUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @variables y::Real, [unit = "m"]
                    @equations y ~ a + b
                end
                """,
                line = 5,
                col = 24,
                contains = "cannot add [s] to [m] in \"y ~ a + b\"",
            ),
            (
                name = "subtraction",
                source = """
                @block SubtractUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @variables y::Real, [unit = "s"]
                    @equations y ~ b - a
                end
                """,
                line = 5,
                col = 24,
                contains = "cannot subtract [m] from [s]",
            ),
            (
                name = "equation",
                source = """
                @block EquateUnit begin
                    @parameters a::Real = 1.0, [unit = "s"]
                    @variables y::Real, [unit = "m"]
                    @equations y ~ a
                end
                """,
                line = 4,
                col = 20,
                contains = "cannot equate [s] with [m] in \"y ~ a\"",
            ),
            (
                name = "product",
                source = """
                @block MultiplyUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @variables y::Real, [unit = "m"]
                    @equations y ~ a * b
                end
                """,
                line = 5,
                col = 20,
                contains = "cannot equate [m*s] with [m]",
            ),
            (
                name = "quotient",
                source = """
                @block DivideUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @variables y::Real, [unit = "m"]
                    @equations y ~ a / b
                end
                """,
                line = 5,
                col = 20,
                contains = "cannot equate [m/s] with [m]",
            ),
            (
                name = "trigonometric argument",
                source = """
                @block SinUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @variables y::Real
                    @equations y ~ sin(a)
                end
                """,
                line = 4,
                col = 24,
                contains = "`sin` needs a dimensionless argument, got [m]",
            ),
            (
                name = "square root of an odd exponent",
                source = """
                @block SqrtUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @variables y::Real
                    @equations y ~ sqrt(a)
                end
                """,
                line = 4,
                col = 20,
                contains = "`sqrt` needs even exponents, got [m]",
            ),
            (
                name = "real exponent",
                source = """
                @block PowUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @variables y::Real
                    @equations y ~ a ^ 0.5
                end
                """,
                line = 4,
                col = 24,
                contains = "must be an integer",
            ),
            (
                name = "parameter exponent",
                source = """
                @block PowParamUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters n::Real = 2.0
                    @variables y::Real
                    @equations y ~ a ^ n
                end
                """,
                line = 5,
                col = 24,
                contains = "must be an integer literal",
            ),
            (
                name = "ifelse branches",
                source = """
                @block IfelseUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @parameters c::Bool = true
                    @variables y::Real
                    @equations y ~ ifelse(c, a, b)
                end
                """,
                line = 6,
                col = 33,
                contains = "the branches of `ifelse` must have one unit: [s] and [m]",
            ),
            (
                name = "comparison",
                source = """
                @block CompareUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @parameters c::Bool = true
                    @variables y::Real
                    @equations y ~ ifelse(a > b, 1.0, 2.0)
                end
                """,
                line = 6,
                col = 31,
                contains = "cannot compare [s] with [m]",
            ),
            (
                name = "min/max",
                source = """
                @block MinUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @variables y::Real
                    @equations y ~ min(a, b)
                end
                """,
                line = 5,
                col = 27,
                contains = "`min` arguments must have one unit: [s] and [m]",
            ),
            (
                name = "ddt",
                source = """
                @block DdtUnit begin
                    @variables a::Real, [unit = "m"]
                    @variables y::Real, [unit = "m/s^2"]
                    @equations y ~ ddt(a)
                end
                """,
                line = 4,
                col = 20,
                contains = "cannot equate [m/s] with [m/s^2]",
            ),
            (
                name = "invalid unit text",
                source = """
                @block BadUnitText begin
                    @parameters a::Real = 1.0, [unit = "m2"]
                    @variables y::Real, [unit = "m"]
                    @equations y ~ a
                end
                """,
                line = 2,
                col = 16,
                contains = "invalid unit \"m2\"",
            ),
            (
                name = "unknown unit",
                source = """
                @block UnknownUnitText begin
                    @parameters a::Real = 1.0, [unit = "furlong"]
                    @variables y::Real
                    @equations y ~ a
                end
                """,
                line = 2,
                col = 16,
                contains = "unknown unit `furlong`",
            ),
            (
                name = "port field",
                source = """
                @block PortUnit begin
                    @ports a::Power{Rotation}
                    @variables y::Real, [unit = "N*m"]
                    @equations y ~ a.f
                end
                """,
                line = 4,
                col = 20,
                contains = "cannot equate [rad/s] with [N*m]",
            ),
            (
                name = "vector literal",
                source = """
                @block VectorUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @parameters b::Real = 1.0, [unit = "s"]
                    @variables v::Vec{2}, [unit = "m"]
                    @equations v ~ [a, b]
                end
                """,
                line = 5,
                col = 24,
                contains = "the elements of a vector literal must have one unit: [s] and [m]",
            ),
            (
                name = "floor",
                source = """
                @block FloorUnit begin
                    @parameters a::Real = 1.0, [unit = "m"]
                    @variables y::Real
                    @equations y ~ floor(a)
                end
                """,
                line = 4,
                col = 26,
                contains = "`floor` needs a dimensionless argument, got [m]",
            ),
            (
                name = "generic effort vs flow",
                source = """
                @block GenericUnit begin
                    @ports p::Power{Generic}
                    @parameters a::Real = 1.0, [unit = "effort"]
                    @variables y::Real, [unit = "flow"]
                    @equations y ~ a
                end
                """,
                line = 5,
                col = 20,
                contains = "cannot equate [effort] with [flow]",
            ),
            (
                name = "time is seconds",
                source = """
                @block TimeUnit begin
                    @variables y::Real
                    @equations y ~ sin(t)
                end
                """,
                line = 3,
                col = 24,
                contains = "`sin` needs a dimensionless argument, got [s]",
            ),
            (
                name = "int start value",
                source = """
                @block IntUnit begin
                    @variables u::Real, [unit = "m/s"]
                    @parameters u0::Real = 0.0, [unit = "s"]
                    @variables y::Real, [unit = "m"]
                    @equations y ~ int(u, u0)
                end
                """,
                line = 5,
                col = 27,
                contains = "the start value of `int` is [s] but the integral is [m]",
            ),
            (
                name = "delay time",
                source = """
                @block DelayUnit begin
                    @ports p::Power{Generic}
                    @variables y::Real, [unit = "flow"]
                    @parameters tau::Real = 0.1, [unit = "m"]
                    @equations y ~ delay(p.f, tau)
                end
                """,
                line = 5,
                col = 31,
                contains = "the delay time must be [s], got [m]",
            ),
            (
                name = "hydraulic port",
                source = """
                @block HydraulicUnit begin
                    @ports p::Power{Hydraulic}
                    @variables y::Real, [unit = "m^3/s"]
                    @equations y ~ p.e
                end
                """,
                line = 4,
                col = 20,
                contains = "cannot equate [Pa] with [m^3/s]",
            ),
        ]
        @test length(cases) >= 15
        for case in cases
            pb = parse_block(case.source; ref = "project:$(case.name)")
            ds = unit_diags(pb)
            # Exactly one unit diagnostic: a mismatch must not cascade into the enclosing
            # equation or into a second operand.
            @test length(ds) == 1
            d = expect_unit(pb, "E006", case.line, case.col; contains = case.contains)
            if d !== nothing
                @test d.severity == "error"
                @test d.block == "project:$(case.name)"
                @test d.source !== nothing
                @test d.source.kind == "project"
                @test d.scope == "@equations" || d.scope == "@parameters"
                @test d.hint !== nothing
            end
        end

        # The message and the hint name both units and the offending term (plan 5.3).
        pb = parse_block(cases[1].source; ref = "project:add")
        d = only(unit_diags(pb))
        @test d.message == "cannot add [s] to [m] in \"y ~ a + b\""
        @test occursin("`b` is [s]", d.hint)
        @test occursin("`a` is [m]", d.hint)

        # A unit error suppresses `block_equations` (J1.1 keeps that rule for every error)
        # but not `check_units` itself.
        @test isempty(block_equations(pb))
        @test length(Units.check_units(pb)) == 1
        @test only(Units.check_units(pb)).code == "E006"

        # A block that does not start at line 1/column 1 still reports absolute source
        # positions and quotes the block's own text (the block slice is not the file).
        offset = parse_block(
            "\n\n    @block OffsetUnit begin\n" *
            "        @parameters a::Real = 1.0, [unit = \"m\"]\n" *
            "        @variables x::Real, [unit = \"s\"]\n" *
            "        @equations x ~ a\n" *
            "    end\n",
        )
        d = expect_unit(offset, "E006", 6, 24; contains = "cannot equate [m] with [s] in \"x ~ a\"")
        @test d !== nothing
    end

    # -----------------------------------------------------------------------------------
    @testset "scale-only differences are E006 (no runtime conversion)" begin
        pb = parse_block(
            """
            @block ScaleUnit begin
                @parameters a::Real = 1.0, [unit = "m"]
                @parameters b::Real = 1.0, [unit = "mm"]
                @variables y::Real, [unit = "m"]
                @equations y ~ a + b
            end
            """;
            ref = "project:scale",
        )
        ds = unit_diags(pb)
        @test length(ds) == 1
        d = only(ds)
        @test d.code == "E006"
        @test d.severity == "error"
        @test occursin("[mm] and [m] differ only in scale", d.message)
        @test occursin("×0.001", d.message)
        @test unit_at(d) == (5, 24)
        @test any(x -> x.code == "E006", check_block(pb))
        @test isempty(block_equations(pb))
        @test only(Units.check_units(pb)).code == "E006"

        # rpm → rad/s is the same case with the 2π/60 factor.
        pb2 = parse_block(
            """
            @block RpmUnit begin
                @parameters w::Real = 0.0, [unit = "rpm"]
                @variables y::Real, [unit = "rad/s"]
                @equations y ~ w
            end
            """,
        )
        ds2 = unit_diags(pb2)
        @test length(ds2) == 1
        @test ds2[1].code == "E006"
        @test occursin("0.10471975511965977", ds2[1].message)
        @test unit_at(ds2[1]) == (4, 20)

        # deg → rad is a scale-only difference on a dimensionless pair.
        pb3 = parse_block(
            """
            @block DegUnit begin
                @parameters a::Real = 0.0, [unit = "deg"]
                @variables y::Real, [unit = "rad"]
                @equations y ~ a
            end
            """,
        )
        @test [x.code for x in unit_diags(pb3)] == ["E006"]
        @test occursin("0.017453292519943295", only(unit_diags(pb3)).message)

        # Equal units produce no unit diagnostic at all.
        clean = parse_block(
            """
            @block CleanUnit begin
                @parameters a::Real = 1.0, [unit = "m"]
                @variables y::Real, [unit = "m"]
                @equations y ~ a
            end
            """,
        )
        @test isempty(unit_diags(clean))
    end

    # -----------------------------------------------------------------------------------
    @testset "physical checks that must pass" begin
        # ddt divides by seconds and int multiplies: the bond-graph storage elements.
        @test Units.dims_of(
            Call(Name(:ddt, test_range()), BGSim.Expr[Name(:q, test_range())], test_range()),
            Units.UnitEnv(Dict(:q => Units.parse_unit("flow*s"))),
        ) == Units.parse_unit("flow")
        @test Units.dims_of(
            Call(
                Name(:int, test_range()),
                BGSim.Expr[Name(:u, test_range()), Lit(0.0, test_range())],
                test_range(),
            ),
            Units.UnitEnv(Dict(:u => Units.parse_unit("m/s"))),
        ) == M

        blocks = [
            # A capacitor on a Generic bond: flow*s/effort is an effort.
            """
            @block Cap begin
                @ports p::Power{Generic}
                @parameters c::Real = 1.0, [unit = "flow*s/effort"]
                @variables q::Real = 0.0, [unit = "flow*s"]
                @equations begin
                    ddt(q) ~ p.f
                    p.e ~ q / c
                end
            end
            """,
            # The same capacitor on an electrical bond, where c is farads at check time.
            """
            @block ElecCap begin
                @ports p::Power{Electrical}
                @parameters c::Real = 1e-6, [unit = "flow*s/effort"]
                @variables v::Real = 0.0, [unit = "V"]
                @equations begin
                    p.f + 0.0 ~ c * ddt(v)
                    p.e ~ v
                end
            end
            """,
            # A mass: force = mass * acceleration.
            """
            @block MassLike begin
                @ports a::Power{Translation}
                @parameters m::Real = 1.0, [unit = "kg"]
                @variables v::Real = 0.0, [unit = "m/s"]
                @equations a.e ~ m * ddt(v)
            end
            """,
            # A rotating inertia.
            """
            @block InertiaLike begin
                @ports a::Power{Rotation}
                @parameters J::Real = 0.01, [unit = "kg*m^2"]
                @variables w::Real = 0.0, [unit = "rad/s"]
                @equations a.e ~ J * ddt(w)
            end
            """,
            # Trig on radians: rad is dimensionless, so sin(w*t + phi) checks.
            """
            @block SineLike begin
                @parameters w::Real = 1.0, [unit = "rad/s"]
                @parameters phi::Real = 0.0, [unit = "rad"]
                @variables y::Real
                @equations y ~ sin(w * t + phi)
            end
            """,
            # Numeric literals are wildcards in a sum and identities in a product.
            """
            @block LiteralLike begin
                @parameters a::Real = 1.0, [unit = "N*m"]
                @variables y::Real, [unit = "N*m"]
                @equations y ~ 2.0 * a + 0.0
            end
            """,
            # A Vec/Mat declaration's unit applies elementwise; dot multiplies.
            """
            @block DotLike begin
                @constants N::Int = 3
                @inputs u::Vec{N}, [unit = "m"]
                @inputs w::Vec{N}, [unit = "s"]
                @variables y::Real, [unit = "m*s"]
                @equations y ~ dot(u, w)
            end
            """,
        ]
        for source in blocks
            pb = parse_block(source; ref = "stdlib:test/Ok")
            @test isempty(unit_diags(pb))
        end

        # `s` is valid on @inputs, @outputs and @constants, and `t` is seconds.
        pb = parse_block(
            """
            @block ScopesLike begin
                @constants c::Real = 2.0, [unit = "s"]
                @inputs u::Real, [unit = "s"]
                @outputs y::Real = 0.0, [unit = "s"]
                @variables x::Real = 0.0, [unit = "s"]
                @equations x ~ u + c - t
            end
            """,
        )
        @test isempty(unit_diags(pb))
        env = Units.unit_env(pb)
        @test env.names[:c] == S
        @test env.names[:u] == S
        @test env.names[:y] == S
        @test env.names[:x] == S
        @test env.names[:t] == S
    end

    # -----------------------------------------------------------------------------------
    @testset "wildcards skip the check (no inference)" begin
        # A declaration without a unit is a wildcard. In a sum, that makes the sum
        # unknown, so no E006 is reported even when the other term and the target
        # disagree (plan 5.3: "a wildcard term skips the check. This is not inference").
        wild_sum = parse_block(
            """
            @block WildSum begin
                @parameters x::Real = 1.0
                @parameters a::Real = 1.0, [unit = "s"]
                @variables y::Real, [unit = "m"]
                @equations y ~ x + a
            end
            """,
        )
        @test isempty(unit_diags(wild_sum))

        wild_ifelse = parse_block(
            """
            @block WildIfelse begin
                @parameters x::Real = 1.0
                @parameters c::Bool = true
                @parameters a::Real = 1.0, [unit = "s"]
                @variables y::Real, [unit = "m"]
                @equations y ~ ifelse(c, x, a)
            end
            """,
        )
        @test isempty(unit_diags(wild_ifelse))

        wild_min = parse_block(
            """
            @block WildMin begin
                @parameters x::Real = 1.0
                @parameters a::Real = 1.0, [unit = "s"]
                @variables y::Real, [unit = "m"]
                @equations y ~ min(x, a)
            end
            """,
        )
        @test isempty(unit_diags(wild_min))

        wild_vector = parse_block(
            """
            @block WildVector begin
                @parameters x::Real = 1.0
                @parameters a::Real = 1.0, [unit = "s"]
                @variables v::Vec{2}, [unit = "m"]
                @equations v ~ [a, x]
            end
            """,
        )
        @test isempty(unit_diags(wild_vector))

        # A unitless comparison is skipped too.
        wild_compare = parse_block(
            """
            @block WildCompare begin
                @parameters x::Real = 1.0
                @parameters a::Real = 1.0, [unit = "s"]
                @variables y::Real
                @equations y ~ ifelse(x > a, 1.0, 2.0)
            end
            """,
        )
        @test isempty(unit_diags(wild_compare))

        # A numeric literal is not a wildcard: `a + 0.0` is still `a`'s unit, so the
        # mismatch with the metre target is reported.
        literal_sum = parse_block(
            """
            @block LiteralSum begin
                @parameters a::Real = 1.0, [unit = "s"]
                @variables y::Real, [unit = "m"]
                @equations y ~ a + 0.0
            end
            """,
        )
        d = expect_unit(literal_sum, "E006", 4, 20; contains = "cannot equate [s] with [m]")
        @test d !== nothing
    end

    # -----------------------------------------------------------------------------------
    @testset "totality: bad ASTs produce no exception" begin
        # Wrong arities, unknown functions, malformed expressions: J1.1 reports those, and
        # the unit pass must stay silent rather than throw.
        sources = [
            """
            @block EmptyArity begin
                @variables y::Real
                @equations y ~ sin()
            end
            """,
            """
            @block EmptyArity2 begin
                @variables y::Real
                @equations y ~ sqrt()
            end
            """,
            """
            @block EmptyArity3 begin
                @variables y::Real
                @equations y ~ dot()
            end
            """,
            """
            @block EmptyArity4 begin
                @variables y::Real
                @equations y ~ ddt()
            end
            """,
            """
            @block UnknownCall begin
                @variables y::Real
                @equations y ~ nosuchfunction(1.0)
            end
            """,
            """
            @block Undeclared begin
                @variables y::Real
                @equations y ~ undeclared + 1.0
            end
            """,
            """
            @block Strings begin
                @variables y::Real
                @equations y ~ "m"
            end
            """,
            """
            @block Junk begin
                @variables y::Real
                @equations y ~ [1.0, 2.0][3]
            end
            """,
        ]
        for source in sources
            pb = parse_block(source)
            @test Units.check_units(pb) isa Vector{Diagnostic}
            @test check_block(pb) isa Vector{Diagnostic}
        end

        # A syntax-error block has no equations at all.
        pb = parse_block("@block Broken begin")
        @test isempty(Units.check_units(pb))
        @test check_block(pb) isa Vector{Diagnostic}
    end

    # -----------------------------------------------------------------------------------
    @testset "all 36 catalog blocks are unit-clean" begin
        catalog = JSON3.read(read(CATALOG_FIXTURE, String))
        @test length(catalog.blocks) == 36
        for blk in catalog.blocks
            ref = String(blk.ref)
            pb = parse_block(String(blk.source); ref = ref, filename = String(blk.path))
            ds = unit_diags(pb)
            isempty(ds) || @info "unexpected unit diagnostic" ref ds
            @test isempty(ds)
            @test all(d -> d.code != "E006", check_block(pb))
        end
    end
end
