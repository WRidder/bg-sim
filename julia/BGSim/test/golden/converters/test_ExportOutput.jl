# Golden test for `stdlib:converters/ExportOutput` (plan section 8, M2 row: Export output),
# through the real pipeline.
#
# The output marker has only an input `u` (the exported interface) and holds its value in an
# internal `sink` so the signal is part of the simulated system. Model: ExportInput 4 ->
# Gain(0.25) -> ExportOutput, so the exported value is 1.0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ExportOutput" begin
    model = bg_model(
        "ExportOutputHoldsInput",
        [
            bg_node("n1", "E1", bg_ref("stdlib:converters/ExportInput");
                params = Dict{String,Any}("value" => "4.0")),
            bg_node("n2", "G1", bg_ref("stdlib:continuous/Gain");
                params = Dict{String,Any}("k" => "0.25")),
            bg_node("n3", "E2", bg_ref("stdlib:converters/ExportOutput")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n2", "y", "n3", "u"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "E2/u", t), 1.0; rtol = 1e-12)
        @test isapprox(bg_value(columns, "E2/sink", t), 1.0; rtol = 1e-12)
    end
end
