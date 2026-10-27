# Golden test for `stdlib:discrete/Not` (plan section 8, M2 row: AND / OR / NOT / XOR),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test toggle (true on odd ticks) drives the NOT on a 1 ms clock.
#
# Reference: the negation of the exact sample sequence; a Bool is recorded as 1 or 0 and the
# comparison is `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Not" begin
    model = dg_model(
        "NotOfBoolSignal",
        [
            dg_node("n1", "T1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_toggle()))),
            dg_node("n2", "N1", bg_ref("stdlib:discrete/Not")),
        ],
        [bg_conn("c1", "signal", "n1", "q", "n2", "u")];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    q = Float64[0, 1, 0, 1, 0, 1, 0, 1, 0]
    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "T1/q", grid) == q
    # Before the first tick the output is its start value (false); from then on it is the
    # negation of the toggle sample taken on the same tick.
    @test dg_values(columns, "N1/y", grid) == vcat(0.0, [1 - q[k] for k in 2:9])
    @test dg_values(columns, "N1/y", grid) == Float64[0, 0, 1, 0, 1, 0, 1, 0, 1]
end
