# Golden test for `stdlib:continuous/Lookup1D` (plan section 8, M2 row: lookup 1D), through
# the real pipeline. The block calls the `interp1` intrinsic (D12), which the lowering
# registers as an opaque function; the run evaluates the numeric table lookup.
#
# Model: a Ramp u = 0.5t (0 to 2.5 over 5 s) over the table x = [0, 1, 2],
# table = [0, 1, 4], so the exact output is
#   y = 0.5t          for t <= 2   (u <= 1),
#   y = 1.5t - 2      for 2 < t < 4 (1 < u < 2),
#   y = 4             for t >= 4   (hold at the last value).
#
# Reference: that analytic piecewise-linear table and its area (an Integrator gives the
# run a state). Tolerance: rtol 1e-6 / atol 1e-9 for the block output, 1e-6 for the area.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Lookup1D" begin
    model = bg_model(
        "Lookup1DOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "0.5", "initial" => "0.0")),
            bg_node("n2", "L1", bg_ref("stdlib:continuous/Lookup1D");
                params = Dict{String,Any}(
                    "x" => "[0.0, 1.0, 2.0]",
                    "table" => "[0.0, 1.0, 4.0]",
                )),
            bg_node("n3", "I1", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n2", "y", "n3", "u"),
        ];
        t_end = 5.0, points = 501,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1

    function exact(t)
        u = 0.5 * t
        u <= 1.0 && return u
        u >= 2.0 && return 4.0
        return 1.0 + 3.0 * (u - 1.0)
    end
    function area(t)
        t <= 2.0 && return 0.25 * t^2
        t <= 4.0 && return 0.75 * t^2 - 2.0 * t + 2.0
        return 4.0 * t - 10.0
    end
    for t in (0.0, 1.0, 2.0, 3.0, 4.0, 4.5, 5.0)
        @test isapprox(bg_value(columns, "L1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/y", t), area(t); rtol = 1e-6, atol = 1e-6)
    end
end
