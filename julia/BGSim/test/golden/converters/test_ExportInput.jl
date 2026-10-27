# Golden test for `stdlib:converters/ExportInput` (plan section 8, M2 row: Export input),
# through the real pipeline.
#
# In simulation an exported input is a source: `y = value`. The model feeds it through a
# `Gain` (k = 2) into an `ExportOutput`, so the whole interface pair is exercised:
#
#   E1/y = 2.5,  G1/y = 5,  E2/sink = 5.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ExportInput" begin
    model = bg_model(
        "ExportInputDrivesOutput",
        [
            bg_node("n1", "E1", bg_ref("stdlib:converters/ExportInput");
                params = Dict{String,Any}("value" => "2.5")),
            bg_node("n2", "G1", bg_ref("stdlib:continuous/Gain");
                params = Dict{String,Any}("k" => "2.0")),
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
        @test isapprox(bg_value(columns, "E1/y", t), 2.5; rtol = 1e-12)
        @test isapprox(bg_value(columns, "G1/y", t), 5.0; rtol = 1e-12)
        @test isapprox(bg_value(columns, "E2/u", t), 5.0; rtol = 1e-12)
        @test isapprox(bg_value(columns, "E2/sink", t), 5.0; rtol = 1e-12)
    end
end
