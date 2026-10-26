# Golden test for `stdlib:sources/Time` (plan section 8, M2 row: the simulation-time
# source), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: the Time source drives an Integrator.
#
# Reference: the analytic solution of the flat model.
#   y(t) = t;   the integrator accumulates it, so Y(t) = t^2/2.
#
# Tolerance: rtol 1e-6 at the sample points and a 1e-8 whole-grid bound (the run itself
# uses reltol 1e-10, abstol 1e-12).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Time source" begin
    model = bg_model(
        "TimeDrivesIntegrator",
        [
            bg_node("n1", "Time1", bg_ref("stdlib:sources/Time")),
            bg_node("n2", "I1", bg_ref("stdlib:continuous/Integrator")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the integrator state

    for t in (0.0, 0.1, 0.35, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "Time1/y", t), t; rtol = 1e-6, atol = 1e-12)
        @test isapprox(bg_value(columns, "I1/y", t), t^2 / 2.0; rtol = 1e-6,
            atol = 1e-12)
    end

    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "Time1/y") .- times)) < 1e-8
    @test maximum(abs.(bg_all(columns, "I1/y") .- times .^ 2 ./ 2.0)) < 1e-8
end
