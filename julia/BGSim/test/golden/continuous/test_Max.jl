# Golden test for `stdlib:continuous/Max` (plan section 8, M2 row: min / max / abs / sign),
# through the real pipeline.
#
# Model: u1 = 1 and u2 = a Ramp from -1 with slope 1; they cross at t = 2.
#
# Reference: y = max(1, -1 + t) = 1 for t < 2 and -1 + t after. Algebraic block, no states.
# Tolerance: rtol 1e-6.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Max" begin
    model = bg_model(
        "MaxOfConstantAndRamp",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "1.0", "initial" => "-1.0")),
            bg_node("n3", "M1", bg_ref("stdlib:continuous/Max")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u1"),
            bg_conn("c2", "signal", "n2", "y", "n3", "u2"),
        ];
        t_end = 3.0, points = 301,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    for t in (0.0, 0.5, 1.0, 1.9, 2.1, 2.5, 3.0)
        @test isapprox(bg_value(columns, "M1/y", t), max(1.0, -1.0 + t); rtol = 1e-6,
            atol = 1e-9)
    end
end
