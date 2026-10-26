# Golden test for `stdlib:continuous/Product` (plan section 8, M2 row: product / divide),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Ramp (`-1 + 2t`) times a Constant 0.5. The product is `-0.5 + t`; the output
# drives an Integrator so the run has a state (a model with no states and no switching
# condition has nothing for the ODE solver to advance).
#
# Reference: the analytic product and its area. Tolerance: rtol 1e-6 / atol 1e-9.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Product" begin
    model = bg_model(
        "ProductOfViews",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "2.0", "initial" => "-1.0")),
            bg_node("n2", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.5")),
            bg_node("n3", "M1", bg_ref("stdlib:continuous/Product")),
            bg_node("n4", "I1", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u1"),
            bg_conn("c2", "signal", "n2", "y", "n3", "u2"),
            bg_conn("c3", "signal", "n3", "y", "n4", "u"),
        ];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1

    for t in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0)
        @test isapprox(bg_value(columns, "M1/y", t), -0.5 + t; rtol = 1e-6, atol = 1e-9)
        # The integrator also proves the signal is consumed: its analytic area is
        # -t/2 + t^2/2.
        @test isapprox(bg_value(columns, "I1/y", t), -0.5 * t + 0.5 * t^2; rtol = 1e-6,
            atol = 1e-9)
    end
    @test maximum(abs.(bg_all(columns, "M1/y") .- (-0.5 .+ columns["time"]))) < 1e-9
end
