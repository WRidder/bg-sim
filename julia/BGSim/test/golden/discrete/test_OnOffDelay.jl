# Golden test for `stdlib:discrete/OnOffDelay` (plan section 8, M2 row: On-delay / off-delay
# timer), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: an inline discrete pattern source on a 1 ms clock produces a square wave that is high
# for two ticks every four ticks (`mod(k, 4) == 1 || mod(k, 4) == 2`). Three timers see it:
#   A  t_on = 2 ms, t_off = 1 ms        B  t_on = 0, t_off = 0        C  t_on = 3 ms, t_off = 2 ms
#
# Reference: the output turns on after the input has been high for t_on and off after it has
# been low for t_off; the timers restart when the input changes:
#   input: 0 1 1 0 0 1 1 0 0       A: 0 0 1 0 0 0 1 0 0
#   B: 0 1 1 0 0 1 1 0 0           C: 0 0 0 0 0 0 0 0 0
# The comparison is `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: OnOffDelay" begin
    params(t_on, t_off) = Dict{String,Any}("t_on" => string(t_on), "t_off" => string(t_off))

    model = dg_model(
        "OnOffDelaySquareWave",
        [
            dg_node("n1", "U1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_pattern(
                    expr = "mod(k, 4) == 1 || mod(k, 4) == 2")))),
            dg_node("n2", "A", bg_ref("stdlib:discrete/OnOffDelay");
                params = params(0.002, 0.001)),
            dg_node("n3", "B", bg_ref("stdlib:discrete/OnOffDelay");
                params = params(0.0, 0.0)),
            dg_node("n4", "C", bg_ref("stdlib:discrete/OnOffDelay");
                params = params(0.003, 0.002)),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n1", "y", "n3", "u"),
            bg_conn("c3", "signal", "n1", "y", "n4", "u"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "U1/y", grid) == Float64[0, 1, 1, 0, 0, 1, 1, 0, 0]
    @test dg_values(columns, "A/y", grid) == Float64[0, 0, 1, 0, 0, 0, 1, 0, 0]
    @test dg_values(columns, "B/y", grid) == Float64[0, 1, 1, 0, 0, 1, 1, 0, 0]
    @test dg_values(columns, "C/y", grid) == zeros(9)

    # The on-delay timer counts the high ticks and restarts on every low tick.
    @test bg_value(columns, "A/ton", 0.001) == 0.001
    @test bg_value(columns, "A/ton", 0.002) == 0.002
    @test bg_value(columns, "A/ton", 0.005) == 0.001
    @test bg_value(columns, "A/toff", 0.003) == 0.001
    # With no delays the output follows the input with one tick of internal state.
    @test dg_values(columns, "B/y", grid) == dg_values(columns, "U1/y", grid)
end
