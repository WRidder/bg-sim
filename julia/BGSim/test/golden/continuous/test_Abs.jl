# Golden test for `stdlib:continuous/Abs` (plan section 8, M2 row: min / max / abs / sign),
# through the real pipeline.
#
# Model: a Ramp from -1 with slope 0.5 (u = -1 + 0.5t, zero at t = 2) drives |u|.
#
# Reference: y = |-1 + 0.5t|. The kink at t = 2 is a nonsmooth event the collector sees, so
# the output grid also holds the switching instant. Algebraic block, no states.
# Tolerance: rtol 1e-6 / atol 1e-9.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Abs" begin
    model = bg_model(
        "AbsOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "0.5", "initial" => "-1.0")),
            bg_node("n2", "A1", bg_ref("stdlib:continuous/Abs")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 4.0, points = 401,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    for t in (0.0, 0.5, 1.0, 1.9, 2.0, 2.1, 3.0, 4.0)
        @test isapprox(bg_value(columns, "A1/y", t), abs(-1.0 + 0.5 * t); rtol = 1e-6,
            atol = 1e-9)
    end
    @test all(bg_all(columns, "A1/y") .>= 0.0)
end
