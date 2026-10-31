# Golden test for `stdlib:discrete/DiscreteDerivative`, through the real pipeline.
#
# A discrete ramp that rises by 3 every 1 ms tick, sampled by the derivative on the same
# 1 ms clock: y[k] = gain*(u[k] - u[k-1])/Ts = gain*3000 after the first tick, and
# gain*(u[1] - initial)/Ts at the first tick. A 2 ms clock sees steps of 6 per period, the
# same slope. Every value is exact in Float64.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: DiscreteDerivative" begin
    model = dg_model("DiscreteDerivativeRamp",
        [dg_node("n1", "R", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(increment = 3.0, period = 1.0e-3)))),
            dg_node("n2", "D1", bg_ref("stdlib:discrete/DiscreteDerivative")),
            dg_node("n3", "D2", bg_ref("stdlib:discrete/DiscreteDerivative");
                params = Dict{String,Any}("gain" => "0.5", "initial" => "3.0")),
            dg_node("n4", "D3", bg_ref("stdlib:discrete/DiscreteDerivative");
                constants = Dict{String,Any}("sample_period" => 2.0e-3))],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u"), bg_conn("c2", "signal", "n1", "y", "n3", "u"),
            bg_conn("c3", "signal", "n1", "y", "n4", "u")];
        t_end = 0.006, points = 13)
    columns, result, _ = bg_run(model)
    @test result.status == "done"
    # Between ticks (0.5 ms after each), the held values.
    mid = [0.0005 + k * 1e-3 for k in 0:5]
    # Tick 1 (t = 1 ms): u = 3, previous = initial 0 -> 3000; then 3000 at every tick.
    @test dg_values(columns, "D1/y", mid) == [0.0, 3000.0, 3000.0, 3000.0, 3000.0, 3000.0]
    # initial = 3 = u[1], so the first tick gives 0; gain 0.5 halves the slope.
    @test dg_values(columns, "D2/y", mid) == [0.0, 0.0, 1500.0, 1500.0, 1500.0, 1500.0]
    # The 2 ms clock: tick at 2 ms sees u = 6 -> 3000, then (12 - 6)/0.002 = 3000.
    @test dg_values(columns, "D3/y", mid) == [0.0, 0.0, 3000.0, 3000.0, 3000.0, 3000.0]
end
