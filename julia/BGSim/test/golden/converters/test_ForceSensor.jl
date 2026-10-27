# Golden test for `stdlib:converters/ForceSensor` (plan section 8, M2 row: Force/torque
# sensor), through the real pipeline.
#
# Model: a `VelocitySource` (v = 1) driven by Constant 0.6 pulls through the sensor into a
# 500 N*s/m `Damper` and a `Fixed` end. The sensor is transparent in velocity and reads the
# series force:
#
#   a.f = b.f = 0.6 m/s,  y = a.e = 300 N,  b.e = -300 N,
#   P_a + P_b = 0 (no energy stored or lost in the sensor).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ForceSensor" begin
    v = 0.6
    d = 500.0
    force = d * v
    model = bg_model(
        "ForceSensorInSeries",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v))),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "1.0")),
            bg_node("n3", "F2", bg_ref("stdlib:converters/ForceSensor")),
            bg_node("n4", "D1", bg_ref("stdlib:translation/Damper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "F2/a.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "F2/b.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "F2/y", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "F2/a.e", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "F2/b.e", t), -force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.e", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), -force; rtol = 1e-9)
        # The series sensor is power neutral, and the damper takes the whole 180 W.
        @test abs(bg_value(columns, "F2/a.P", t) + bg_value(columns, "F2/b.P", t)) <= 1e-12
        @test isapprox(bg_value(columns, "D1/a.P", t), force * v; rtol = 1e-9)
    end
end
