# Golden test for `stdlib:discrete/Memory`, through the real pipeline.
#
# 1. A discrete ramp (one step every 0.5 ms) through Memory on a 1 ms clock: y[k] is the
#    input value before tick k, `initial` at the first tick; the same values as UnitDelay.
# 2. Two Memory blocks in a cycle (M1 reads M2, M2 reads M1) are legal because Memory reads
#    previous(u): no E105, and the two values swap on every tick, starting from the initials.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Memory" begin
    model = dg_model("MemoryRamp",
        [dg_node("n1", "R", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(period = 1.0e-3)))),
            dg_node("n2", "M", bg_ref("stdlib:discrete/Memory"); params = Dict{String,Any}("initial" => "7.0")),
            dg_node("n3", "D", bg_ref("stdlib:discrete/UnitDelay"); params = Dict{String,Any}("initial" => "7.0")),
            dg_node("n4", "F", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(period = 5.0e-4)))),
            dg_node("n5", "MF", bg_ref("stdlib:discrete/Memory"))],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u"), bg_conn("c2", "signal", "n1", "y", "n3", "u"),
            bg_conn("c3", "signal", "n4", "y", "n5", "u")];
        t_end = 0.004, points = 9)
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test flat.stats.states == 0
    grid = dg_grid(0.004; points = 9)
    # The same clock: the ramp ticks 1, 2, 3, ... and Memory publishes the value before.
    @test dg_values(columns, "M/y", grid) == Float64[0, 0, 7, 7, 1, 1, 2, 2, 3]
    @test dg_values(columns, "M/y", grid) == dg_values(columns, "D/y", grid)
    # A ramp on a 0.5 ms clock: initial (0) at the first tick, then the latest value before
    # each 1 ms tick (3 at 2 ms, 5 at 3 ms).
    @test dg_values(columns, "MF/y", grid) == Float64[0, 0, 0, 0, 3, 3, 5, 5, 7]

    model = dg_model("MemoryCycle",
        [dg_node("n1", "M1", bg_ref("stdlib:discrete/Memory"); params = Dict{String,Any}("initial" => "1.0")),
            dg_node("n2", "M2", bg_ref("stdlib:discrete/Memory"); params = Dict{String,Any}("initial" => "2.0"))],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u"), bg_conn("c2", "signal", "n2", "y", "n1", "u")];
        t_end = 0.004, points = 5)
    columns, result, flat = bg_run(model)
    @test !any(d -> d.code == "E105", flat.diagnostics)
    @test result.status == "done"
    grid = dg_grid(0.004; points = 5)
    @test dg_values(columns, "M1/y", grid) == Float64[0, 1, 2, 1, 2]
    @test dg_values(columns, "M2/y", grid) == Float64[0, 2, 1, 2, 1]
end
