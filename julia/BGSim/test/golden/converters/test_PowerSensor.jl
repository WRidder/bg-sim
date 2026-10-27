# Golden test for `stdlib:converters/PowerSensor` (plan section 8, M2 row: Power sensor),
# through the real pipeline.
#
# Model: a bond-graph chain Sf(2) -> PowerSensor -> R(3). The sensor is a transparent
# two-port on the bond: `a.f = b.f`, `a.e = b.e`, and `y = a.e*a.f`. A bond negates the
# flow from one port to the other, so the sensor's `a` sees -2 and reports the signed power
# into that port, -12 W; the resistor sees +12 W. The Generic island adopts no concrete
# domain, so W205 (dimensionless Generic island) is the expected warning.
#
#   e = r*|f| = 6, a.f = b.f = -2, y = a.e*a.f = -12 W, R.p.P = +12 W.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: PowerSensor" begin
    f = 2.0
    r = 3.0
    power = r * f * f
    model = bg_model(
        "PowerSensorOnGenericBond",
        [
            bg_node("n1", "Sf1", bg_ref("stdlib:bondgraph/Sf");
                params = Dict{String,Any}("f" => string(f))),
            bg_node("n2", "P1", bg_ref("stdlib:converters/PowerSensor")),
            bg_node("n3", "R1", bg_ref("stdlib:bondgraph/R");
                params = Dict{String,Any}("r" => string(r))),
        ],
        [
            bg_conn("c1", "bond", "n1", "p", "n2", "a"),
            bg_conn("c2", "bond", "n2", "b", "n3", "p"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "P1/a.f", t), -f; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/b.f", t), -f; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/a.e", t), r * f; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/b.e", t), r * f; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/y", t), -power; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/a.P", t), -power; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/b.P", t), -power; rtol = 1e-9)
        @test isapprox(bg_value(columns, "R1/p.P", t), power; rtol = 1e-9)
        @test isapprox(bg_value(columns, "Sf1/p.P", t), power; rtol = 1e-9)
    end
end
