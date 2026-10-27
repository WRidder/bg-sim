# Golden test for `stdlib:converters/PositionSensor` (plan section 8, M2 row: Position
# sensor), through the real pipeline.
#
# Model: a `VelocitySource` holds a translation node at 0.6 m/s against a `Damper`
# (d = 500); the sensor is a third branch on the same wire. It draws no force
# (`a.e = 0`), so it only integrates the node velocity:
#
#   y(t) = 0.6*t m,  a.f = 0.6 m/s,  a.e = 0,  a.P = 0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: PositionSensor" begin
    v = 0.6
    model = bg_model(
        "PositionSensorOnVelocityNode",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v))),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "1.0")),
            bg_node("n3", "D1", bg_ref("stdlib:translation/Damper");
                params = Dict{String,Any}("d" => "500.0")),
            bg_node("n4", "P1", bg_ref("stdlib:converters/PositionSensor")),
            bg_node("n5", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n2", "a", "n4", "a"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 1                 # the integrated position
    for t in (0.0, 0.002, 0.005, 0.01)
        @test isapprox(bg_value(columns, "P1/a.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/y", t), v * t; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "P1/a.e", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "P1/a.P", t), 0.0; atol = 1e-12)
        # The sensor does not disturb the damper force balance.
        @test isapprox(bg_value(columns, "D1/a.e", t), 500.0 * v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), -500.0 * v; rtol = 1e-9)
    end
end
