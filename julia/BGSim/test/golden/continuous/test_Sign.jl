# Golden test for `stdlib:continuous/Sign` (plan section 8, M2 row: min / max / abs / sign),
# through the real pipeline.
#
# Model: a Ramp from -1 with slope 0.75 (u = -1 + 0.75t, zero at t = 4/3, which is not an
# output-grid point) drives sign(u).
#
# Reference: y = -1 while u < 0 and +1 after the zero crossing. Algebraic block, no states.
# Tolerance: atol 1e-9 (the values are constant).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Sign" begin
    model = bg_model(
        "SignOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "0.75", "initial" => "-1.0")),
            bg_node("n2", "G1", bg_ref("stdlib:continuous/Sign")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    for t in (0.0, 0.5, 1.0, 1.3)
        @test isapprox(bg_value(columns, "G1/y", t), -1.0; atol = 1e-9)
    end
    for t in (1.4, 1.5, 2.0)
        @test isapprox(bg_value(columns, "G1/y", t), 1.0; atol = 1e-9)
    end
end
