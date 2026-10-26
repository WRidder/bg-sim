# Golden test for `stdlib:continuous/Lookup2D` (plan section 8, M2 row: lookup 2D), through
# the real pipeline. The block calls the `interp2` intrinsic (D12), which the lowering
# registers as an opaque bilinear lookup.
#
# Model: u = 0.25t (0 to 1.25 over 5 s), v = 0.4, over the 3x3 grid with x = y = [0, 1, 2]
# and table[i,j] = x_j + y_i. Bilinear interpolation of a linear surface is exact, so
#   y = u + v = 0.25t + 0.4   (clamped at the grid edges, which this run does not reach).
#
# Reference: that analytic plane, and its area (an Integrator gives the run a state).
# Tolerance: rtol 1e-6 / atol 1e-9 for the block output and 1e-6 for the area.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Lookup2D" begin
    model = bg_model(
        "Lookup2DOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "0.25", "initial" => "0.0")),
            bg_node("n2", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.4")),
            bg_node("n3", "L1", bg_ref("stdlib:continuous/Lookup2D");
                params = Dict{String,Any}(
                    "breaks" => "[0.0 1.0 2.0; 0.0 1.0 2.0]",
                    "table" => "[0.0 1.0 2.0; 1.0 2.0 3.0; 2.0 3.0 4.0]",
                )),
            bg_node("n4", "I1", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n3", "v"),
            bg_conn("c3", "signal", "n3", "y", "n4", "u"),
        ];
        t_end = 5.0, points = 501,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1

    for t in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
        @test isapprox(bg_value(columns, "L1/y", t), 0.25 * t + 0.4; rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/y", t), 0.125 * t^2 + 0.4 * t; rtol = 1e-6,
            atol = 1e-6)
    end
    # Off-grid points too: the bilinear surface is exact everywhere on the plane.
    @test isapprox(bg_value(columns, "L1/y", 2.37), 0.25 * 2.37 + 0.4; rtol = 1e-6,
        atol = 1e-9)
end
