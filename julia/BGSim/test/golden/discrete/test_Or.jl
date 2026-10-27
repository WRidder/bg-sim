# Golden test for `stdlib:discrete/Or` (plan section 8, M2 row: AND / OR / NOT / XOR), through
# the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test toggle (true on odd ticks) and a discrete test pattern (`k >= 2`)
# drive the two-input OR on a 1 ms clock.
#
# Reference: the truth table on the exact sample sequences; a Bool is recorded as 1 or 0 and
# the comparison is `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Or" begin
    model = dg_model(
        "OrOfTwoBoolSignals",
        [
            dg_node("n1", "T1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_toggle()))),
            dg_node("n2", "P1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_pattern(expr = "k >= 2")))),
            dg_node("n3", "O1", bg_ref("stdlib:discrete/Or")),
        ],
        [
            bg_conn("c1", "signal", "n1", "q", "n3", "u1"),
            bg_conn("c2", "signal", "n2", "y", "n3", "u2"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    q = Float64[0, 1, 0, 1, 0, 1, 0, 1, 0]
    p = Float64[0, 0, 1, 1, 1, 1, 1, 1, 1]
    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "O1/y", grid) == Float64[q[k] == 1.0 || p[k] == 1.0 for k in 1:9]
    @test dg_values(columns, "O1/y", grid) == Float64[0, 1, 1, 1, 1, 1, 1, 1, 1]
    # At t = 0 both inputs are still false; from the first tick on the toggle carries it.
    @test bg_value(columns, "O1/y", 0.0) == 0.0
    @test bg_value(columns, "O1/y", 0.001) == 1.0
end
