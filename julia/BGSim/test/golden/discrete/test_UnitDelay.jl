# Golden test for `stdlib:discrete/UnitDelay` (plan section 8, M2 row: Unit delay (z^-1)),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Constant and a discrete test ramp (one step every 0.5 ms) each drive a UnitDelay
# on its 1 ms clock; a third UnitDelay has the initial value 7.0.
#
# Reference: y[k] = u[k-1] for k >= 2 and y[slot 1] = initial, where slot 1 is the first tick;
# before it the output holds its declared start value. Every value is an exact Float64 (a
# constant and whole-number ramp samples), so the sequences are compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: UnitDelay" begin
    model = dg_model(
        "UnitDelayAgainstExactSequence",
        [
            dg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "2.5")),
            dg_node("n2", "R1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(period = 5.0e-4)))),
            dg_node("n3", "D1", bg_ref("stdlib:discrete/UnitDelay")),
            dg_node("n4", "D2", bg_ref("stdlib:discrete/UnitDelay")),
            dg_node("n5", "D3", bg_ref("stdlib:discrete/UnitDelay");
                params = Dict{String,Any}("initial" => "7.0")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u"),
            bg_conn("c3", "signal", "n1", "y", "n5", "u"),
        ];
        t_end = 0.004, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0                 # the delays are held values, not states

    grid = dg_grid(0.004; points = 9)            # 0.5 ms spacing

    # The 1 ms clock samples the 0.5 ms ramp at 2, 4, 6, 8 and delays each sample by one tick.
    @test dg_values(columns, "D2/y", grid) == Float64[0, 0, 0, 0, 2, 2, 4, 4, 6]
    # The constant is delayed once and then held.
    @test dg_values(columns, "D1/y", grid) == Float64[0, 0, 0, 0, 2.5, 2.5, 2.5, 2.5, 2.5]
    # `initial` is the value at the first tick; the ramp then continues from the delayed input.
    @test dg_values(columns, "D3/y", grid) == Float64[0, 0, 7, 7, 2.5, 2.5, 2.5, 2.5, 2.5]

    # A held output only moves on its ticks: between two ticks the value is constant.
    @test bg_value(columns, "D2/y", 0.002) == bg_value(columns, "D2/y", 0.0025)
    # Every 0.5 ms tick changes the ramp, so each of the eight ticks writes a left/right pair
    # instead of the single grid row at that instant: 9 grid rows + 8 extra.
    @test length(columns["time"]) == 9 + 8
end
