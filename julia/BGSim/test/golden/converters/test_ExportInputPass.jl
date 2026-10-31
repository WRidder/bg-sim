# Golden test for `stdlib:converters/ExportInputPass` (plan/EXPORT_PLAN.md X-EX1), through the
# real pipeline.
#
# In simulation the pass-through input marker is inert: `y = u`. A Ramp (slope 2) feeds it,
# a Gain (k = 3) follows, so G1/y = 6 t. Its `value` (here 1.5) is only the start value of
# the exported input. `Export.host_inputs` (what the export and the X-EX1 reference run use)
# cuts the wire: then `y = value`, so G1/y = 4.5 at every instant.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden
using BGSim

@testset "golden: ExportInputPass" begin
    model = bg_model(
        "ExportInputPassThrough",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}("slope" => "2.0", "t_start" => "0.0")),
            bg_node("n2", "P1", bg_ref("stdlib:converters/ExportInputPass");
                params = Dict{String,Any}("value" => "1.5")),
            bg_node("n3", "G1", bg_ref("stdlib:continuous/Gain");
                params = Dict{String,Any}("k" => "3.0")),
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
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "P1/y", t), 2t; atol = 1e-12)
        @test isapprox(bg_value(columns, "G1/y", t), 6t; atol = 1e-12)
    end

    host = BGSim.Export.host_inputs(flat)
    @test BGSim.compile_key(host) != BGSim.compile_key(flat)
    @test BGSim.Export.host_inputs(host) === host            # idempotent
    hosted = BGSim.simulate(host; settings = Dict("t_end" => 0.01,
        "output" => Dict("mode" => "points", "points" => 11)))
    @test hosted.status == "done"
    hcols = BondGraphGolden.bg_columns(hosted.run_dir)
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(hcols, "P1/y", t), 1.5; atol = 1e-12)
        @test isapprox(bg_value(hcols, "G1/y", t), 4.5; atol = 1e-12)
        @test isapprox(bg_value(hcols, "P1/u", t), 2t; atol = 1e-12)   # the cut wire still records
    end
end
