# Golden test for `stdlib:discrete/RateTransition` (plan section 8, M2 row: Rate transition),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: an input clock every 5 ms samples a discrete test ramp that steps every 0.5 ms; an
# output clock every 1 ms publishes the most recent sample.
#
# Reference: y is the last sample of the 5 ms clock, so it reads 0 until 5 ms, 10 from 5 ms on
# (the ramp is 2 per 0.5 ms, so 10 at 5 ms) and 20 from 10 ms on. Every value is exact.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: RateTransition" begin
    model = dg_model(
        "RateTransitionSlowInputFastOutput",
        [
            dg_node("n1", "R1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(period = 5.0e-4)))),
            dg_node("n2", "T1", bg_ref("stdlib:discrete/RateTransition")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 0.010, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.010; points = 11)           # the 1 ms output clock
    @test dg_values(columns, "T1/y", grid) ==
          Float64[0, 0, 0, 0, 0, 10, 10, 10, 10, 10, 20]

    # The input samples land on the 5 ms clock, not in between.
    @test bg_value(columns, "T1/x", 0.004) == 0.0
    @test bg_value(columns, "T1/x", 0.005) == 10.0
    @test bg_value(columns, "T1/x", 0.006) == 10.0
    # The output clock is faster than the input clock, so the output is refreshed four times
    # with the same sample between two input ticks.
    @test bg_value(columns, "T1/y", 0.006) == bg_value(columns, "T1/y", 0.009) == 10.0
    @test bg_value(columns, "R1/y", 0.006) == 12.0     # the ramp itself keeps moving
end
