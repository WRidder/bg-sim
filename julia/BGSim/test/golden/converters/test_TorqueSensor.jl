# Golden test for `stdlib:converters/TorqueSensor` (plan section 8, M2 row: Force/torque
# sensor), through the real pipeline.
#
# Model: a `SpeedSource` (w = 2.5 rad/s) drives through the sensor into a 0.4 N*m*s/rad
# `RotationalDamper` and a `FixedShaft`. The sensor is transparent in speed and reads the
# series torque:
#
#   a.f = b.f = 2.5 rad/s,  y = a.e = 1.0 N*m,  b.e = -1.0 N*m,
#   P_a + P_b = 0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: TorqueSensor" begin
    w = 2.5
    d = 0.4
    torque = d * w
    model = bg_model(
        "TorqueSensorInSeries",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "T2", bg_ref("stdlib:converters/TorqueSensor")),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
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
        @test isapprox(bg_value(columns, "T2/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T2/b.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T2/y", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T2/a.e", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T2/b.e", t), -torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.e", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.e", t), -torque; rtol = 1e-9)
        @test abs(bg_value(columns, "T2/a.P", t) + bg_value(columns, "T2/b.P", t)) <= 1e-12
        @test isapprox(bg_value(columns, "D1/a.P", t), torque * w; rtol = 1e-9)
    end
end
