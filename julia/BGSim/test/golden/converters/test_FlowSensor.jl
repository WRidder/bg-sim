# Golden test for `stdlib:converters/FlowSensor` (plan section 8, M2 row: Pressure/flow
# sensor), through the real pipeline.
#
# Model: a `FlowSource` (Q = 1e-5 m^3/s) feeds the sensor in series and the sensor returns
# to a `Tank`. The sensor drops no pressure and reads the flow through it:
#
#   y = a.f = -Q (the source draws Q from the node),  b.f = +Q,  a.e = b.e = p_tank.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: FlowSensor" begin
    Q = 1.0e-5
    p_tank = 1.0e5
    model = bg_model(
        "FlowSensorInSeries",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "F1", bg_ref("stdlib:hydraulic/FlowSource");
                params = Dict{String,Any}("Q" => string(Q))),
            bg_node("n3", "S1", bg_ref("stdlib:converters/FlowSensor")),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_tank))),
            bg_node("n5", "T2", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_tank))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n2", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "S1/y", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S1/a.f", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S1/b.f", t), Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S1/a.e", t), p_tank; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S1/b.e", t), p_tank; rtol = 1e-9)
        # No pressure drop: the sensor is power neutral and the tank receives Q.
        @test isapprox(bg_value(columns, "S1/a.P", t) + bg_value(columns, "S1/b.P", t),
            0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "T1/a.f", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T2/a.f", t), Q; rtol = 1e-9)
    end
end
