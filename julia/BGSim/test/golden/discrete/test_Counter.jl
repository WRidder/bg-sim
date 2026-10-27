# Golden test for `stdlib:discrete/Counter` (plan section 8, M2 row: Counter), through the real
# pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: two inline discrete pattern sources on a 1 ms clock produce a trigger that is high on
# every even tick (`mod(k, 2) == 0`) and a reset pulse at tick 7 (`k == 7`). Two counters see
# both signals: A wraps at 3 with step 1, B stops at 2 with step 2.
#
# Reference: the count starts at lower on the first tick, adds step on every rising edge, wraps
# to lower or stops at upper, and resets to lower while `reset` is high:
#   A: 0 0 1 1 2 2 3 0 1        B: 0 0 2 2 2 2 2 0 2
# The counts are integers, so the sequences are compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Counter" begin
    model = dg_model(
        "CounterEdgesWrapAndReset",
        [
            dg_node("n1", "TR", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_pattern(expr = "mod(k, 2) == 0")))),
            dg_node("n2", "RS", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_pattern(expr = "k == 7")))),
            dg_node("n3", "A", bg_ref("stdlib:discrete/Counter");
                params = Dict{String,Any}("lower" => "0", "upper" => "3", "step" => "1",
                    "wrap" => "1")),
            dg_node("n4", "B", bg_ref("stdlib:discrete/Counter");
                params = Dict{String,Any}("lower" => "0", "upper" => "2", "step" => "2",
                    "wrap" => "0")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "trigger"),
            bg_conn("c2", "signal", "n2", "y", "n3", "reset"),
            bg_conn("c3", "signal", "n1", "y", "n4", "trigger"),
            bg_conn("c4", "signal", "n2", "y", "n4", "reset"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "A/y", grid) == Float64[0, 0, 1, 1, 2, 2, 3, 0, 1]
    @test dg_values(columns, "B/y", grid) == Float64[0, 0, 2, 2, 2, 2, 2, 0, 2]

    # The trigger itself, so the reference of the edges is visible in the run.
    @test dg_values(columns, "TR/y", grid) == Float64[0, 0, 1, 0, 1, 0, 1, 0, 1]
    @test dg_values(columns, "RS/y", grid) == Float64[0, 0, 0, 0, 0, 0, 0, 1, 0]

    # A: the third rising edge wraps from 3 to lower on the next edge (the reset at tick 7 does
    # not hide it: 3 -> reset 0 -> 1). B: 2 + 2 > 2 stops at upper, then the reset clears it.
    @test bg_value(columns, "A/y", 0.007) == 0
    @test bg_value(columns, "A/y", 0.006) == 3
    @test bg_value(columns, "B/y", 0.006) == 2
    # A trigger that stays high for two ticks counts only once (rising edge only).
    @test bg_value(columns, "A/tp", 0.003) == 0.0     # trigger low again
end
