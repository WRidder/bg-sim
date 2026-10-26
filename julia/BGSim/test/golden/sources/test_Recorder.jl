# Golden test for `stdlib:sources/Recorder` (plan section 8, M2 row: the recorder sink,
# a no-op whose decimation is ignored), through the real pipeline
# (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Every signal is recorded anyway (D15), so a Recorder neither changes the simulation nor
# the data stream; its `decimation` parameter is accepted and ignored. Its inputs are passed
# through an internal `sink` copy so that `block.check` has no unused declaration.
#
# Model: a Sine (1 rad/s) drives a Recorder with decimation 7, and in a second run with
# decimation 1. Reference: y(t) = sin(t), and the two decimation settings produce identical
# runs (same output grid, same values, all signals recorded).
#
# Tolerance: rtol 1e-6 against the analytic sine; the two runs are compared exactly.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Recorder sink (no-op)" begin
    sine(t) = sin(t)

    function recorder_model(name, decimation)
        return bg_model(
            name,
            [
                bg_node("n1", "Sine1", bg_ref("stdlib:sources/Sine");
                    params = Dict{String,Any}("amplitude" => "1.0",
                        "frequency" => "1.0", "phase" => "0.0", "offset" => "0.0")),
                bg_node("n2", "Rec1", bg_ref("stdlib:sources/Recorder");
                    params = Dict{String,Any}("decimation" => string(decimation))),
            ],
            [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
            t_end = 1.0, points = 101,
        )
    end

    columns, result, flat = bg_run(recorder_model("SineWithRecorder", 7))
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0                 # a recorder adds no dynamics

    for t in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "Sine1/y", t), sine(t); rtol = 1e-6,
            atol = 1e-9)
        @test bg_value(columns, "Rec1/u[1]", t) == bg_value(columns, "Sine1/y", t)
        @test bg_value(columns, "Rec1/sink[1]", t) == bg_value(columns, "Sine1/y", t)
    end

    # Decimation 7 is ignored: the run is identical to decimation 1, and every signal is
    # present in both files (D15).
    other, other_result, _ = bg_run(recorder_model("SineWithRecorder", 1))
    @test other_result.status == "done"
    @test columns["time"] == other["time"]
    @test bg_all(columns, "Sine1/y") == bg_all(other, "Sine1/y")
    @test bg_all(columns, "Rec1/sink[1]") == bg_all(other, "Rec1/sink[1]")
    @test maximum(abs.(bg_all(columns, "Sine1/y") .- sine.(columns["time"]))) < 1e-8
end
