# Golden test for `stdlib:discrete/ZOH` (plan section 8, M2 row: Zero-order hold), through the
# real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test ramp steps every 0.5 ms; the ZOH samples it on its 1 ms clock.
#
# Reference: y is the input sample taken at the tick and held until the next one, so at a tick
# instant it equals the ramp value at that instant and between two ticks it does not move.
# The values are whole numbers, so they are compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ZOH" begin
    model = dg_model(
        "ZeroOrderHoldAgainstExactStaircase",
        [
            dg_node("n1", "R1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(period = 5.0e-4)))),
            dg_node("n2", "Z1", bg_ref("stdlib:discrete/ZOH")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 0.004, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.004; points = 9)            # 0.5 ms spacing, ticks at 1, 2, 3, 4 ms
    # The ramp is 0, 1, 2, ... every 0.5 ms and the ZOH samples it every 1 ms.
    @test dg_values(columns, "Z1/y", grid) == Float64[0, 0, 2, 2, 4, 4, 6, 6, 8]
    # Between two ticks the output is exactly constant (this is the hold, not an interpolation).
    @test bg_value(columns, "Z1/y", 0.001) == bg_value(columns, "Z1/y", 0.0015) == 2.0
    @test bg_value(columns, "Z1/y", 0.002) == bg_value(columns, "Z1/y", 0.0025) == 4.0
    # The input keeps moving between the ticks.
    @test bg_value(columns, "R1/y", 0.0015) == 3.0
end
