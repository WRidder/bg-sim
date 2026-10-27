# Golden test for `stdlib:converters/CurrentSensor` (plan section 8, M2 row: Voltage/current
# sensor), through the real pipeline.
#
# Model: a 12 V `VoltageSource` drives a 100 Ohm `Resistor` in series with the sensor and a
# `Ground`. The sensor drops no voltage and reads the series current:
#
#   y = p.f = 0.12 A,  p.e - n.e = 0,  p.f + n.f = 0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: CurrentSensor" begin
    V = 12.0
    R = 100.0
    I = V / R
    model = bg_model(
        "CurrentSensorInSeries",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => string(V))),
            bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => string(R))),
            bg_node("n4", "I1", bg_ref("stdlib:converters/CurrentSensor")),
            bg_node("n5", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", "p"),
            bg_conn("c4", "wire", "n4", "n", "n5", "p"),
            bg_conn("c5", "wire", "n2", "n", "n5", "p"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "I1/y", t), I; rtol = 1e-9)
        @test isapprox(bg_value(columns, "I1/p.f", t), I; rtol = 1e-9)
        @test isapprox(bg_value(columns, "I1/n.f", t), -I; rtol = 1e-9)
        @test isapprox(bg_value(columns, "I1/p.e", t) - bg_value(columns, "I1/n.e", t),
            0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "I1/p.P", t) + bg_value(columns, "I1/n.P", t),
            0.0; atol = 1e-12)
        # The resistor carries exactly the sensed current.
        @test isapprox(bg_value(columns, "R1/p.f", t), I; rtol = 1e-9)
        @test isapprox(bg_value(columns, "R1/n.f", t), -I; rtol = 1e-9)
    end
end
