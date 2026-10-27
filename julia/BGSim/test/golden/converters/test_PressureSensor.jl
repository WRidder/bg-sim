# Golden test for `stdlib:converters/PressureSensor` (plan section 8, M2 row: Pressure/flow
# sensor), through the real pipeline.
#
# Two independent hydraulic nodes: a 100 bar `PressureSource` and a 1 bar `Tank`, each with a
# sensor branch. The sensor draws no flow (`a.f = 0`) and reads the node pressure:
#
#   S1/y = 1e7 Pa,   S2/y = 1e5 Pa,
#
# and both sensors are power neutral (flow zero).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: PressureSensor" begin
    p_hi = 1.0e7
    p_lo = 1.0e5
    model = bg_model(
        "PressureSensorsOnSourceAndTank",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "P1", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(p_hi))),
            bg_node("n3", "S1", bg_ref("stdlib:converters/PressureSensor")),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_lo))),
            bg_node("n5", "S2", bg_ref("stdlib:converters/PressureSensor")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n4", "a", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "S1/y", t), p_hi; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S2/y", t), p_lo; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S1/a.f", t), 0.0; atol = 1e-15)
        @test isapprox(bg_value(columns, "S2/a.f", t), 0.0; atol = 1e-15)
        @test isapprox(bg_value(columns, "S1/a.P", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "S2/a.P", t), 0.0; atol = 1e-12)
        # The sources carry no flow because the sensors draw none.
        @test isapprox(bg_value(columns, "P1/a.f", t), 0.0; atol = 1e-15)
        @test isapprox(bg_value(columns, "T1/a.f", t), 0.0; atol = 1e-15)
    end
end
