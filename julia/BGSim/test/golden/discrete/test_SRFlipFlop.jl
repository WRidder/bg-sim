# Golden test for `stdlib:discrete/SRFlipFlop` (plan section 8, M2 row: SR flip-flop), through
# the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: two inline discrete pattern sources on a 1 ms clock set `set` at ticks 2, 3 and 8 and
# `reset` at ticks 5, 6 and 8. Two latches see both, one with `dominant = 0` (set wins) and one
# with `dominant = 1` (reset wins).
#
# Reference: set -> 1, reset -> 0 while only one is high; when both are high the dominant input
# decides. The latch starts reset:
#   dominant set:   0 0 1 1 1 0 0 0 1
#   dominant reset: 0 0 1 1 1 0 0 0 0
# The comparison is `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: SRFlipFlop" begin
    model = dg_model(
        "SRFlipFlopDominance",
        [
            dg_node("n1", "ST", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_pattern(expr = "k == 2 || k == 3 || k == 8")))),
            dg_node("n2", "RS", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_pattern(expr = "k == 5 || k == 6 || k == 8")))),
            dg_node("n3", "QS", bg_ref("stdlib:discrete/SRFlipFlop");
                params = Dict{String,Any}("dominant" => "0")),
            dg_node("n4", "QR", bg_ref("stdlib:discrete/SRFlipFlop");
                params = Dict{String,Any}("dominant" => "1")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "set"),
            bg_conn("c2", "signal", "n2", "y", "n3", "reset"),
            bg_conn("c3", "signal", "n1", "y", "n4", "set"),
            bg_conn("c4", "signal", "n2", "y", "n4", "reset"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "ST/y", grid) == Float64[0, 0, 1, 1, 0, 0, 0, 0, 1]
    @test dg_values(columns, "RS/y", grid) == Float64[0, 0, 0, 0, 0, 1, 1, 0, 1]
    @test dg_values(columns, "QS/q", grid) == Float64[0, 0, 1, 1, 1, 0, 0, 0, 1]
    @test dg_values(columns, "QR/q", grid) == Float64[0, 0, 1, 1, 1, 0, 0, 0, 0]

    # The two latches only differ at tick 8, where both inputs are high.
    @test bg_value(columns, "QS/q", 0.008) == 1.0
    @test bg_value(columns, "QR/q", 0.008) == 0.0
    # Between two pulses the latch holds its state (tick 4 has neither input).
    @test bg_value(columns, "QS/q", 0.004) == 1.0
    @test bg_value(columns, "QS/q", 0.007) == 0.0
end
