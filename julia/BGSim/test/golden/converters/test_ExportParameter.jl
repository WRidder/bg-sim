# Golden test for `stdlib:converters/ExportParameter` (plan section 8, M2 row: Export
# parameter), through the real pipeline.
#
# The marker has no power port and no signal input: it publishes a tunable parameter and
# holds it in an internal `sink` so the value is part of the simulated system. The model is
# the marker alone, which must still flatten and simulate:
#
#   sink = value = 7.5.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ExportParameter" begin
    model = bg_model(
        "ExportParameterMarker",
        [
            bg_node("n1", "P1", bg_ref("stdlib:converters/ExportParameter");
                params = Dict{String,Any}("value" => "7.5")),
        ],
        Any[];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "P1/sink", t), 7.5; rtol = 1e-12)
    end
end
