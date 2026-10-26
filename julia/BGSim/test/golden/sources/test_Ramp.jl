# Golden test for `stdlib:sources/Ramp` (plan section 8, M2 row: the ramp source),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Ramp (t_start = 0.3 s, slope = 2.5, initial = 0.4) drives an Integrator, so the
# source has a real load and the model has one state.
#
# Reference: the analytic solution of the flat model.
#   * y(t) = initial for t <= t_start, then initial + slope*(t - t_start);
#   * the integrator accumulates it: Y(t) = initial*t + slope*max(t - t_start, 0)^2/2.
#
# Tolerance: rtol 1e-6 at the sample points, and a 1e-8 whole-grid bound on both signals
# (the run itself uses reltol 1e-10, abstol 1e-12).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Ramp source" begin
    t_start, slope, initial = 0.3, 2.5, 0.4
    ramp(t) = initial + (t <= t_start ? 0.0 : slope * (t - t_start))
    ramp_integral(t) =
        initial * t + (t <= t_start ? 0.0 : slope * (t - t_start)^2 / 2.0)

    model = bg_model(
        "RampDrivesIntegrator",
        [
            bg_node("n1", "Ramp1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}("t_start" => string(t_start),
                    "slope" => string(slope), "initial" => string(initial))),
            bg_node("n2", "I1", bg_ref("stdlib:continuous/Integrator")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the integrator state

    for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0)
        @test isapprox(bg_value(columns, "Ramp1/y", t), ramp(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/y", t), ramp_integral(t); rtol = 1e-6,
            atol = 1e-9)
    end

    # Before t_start the ramp is flat at `initial`.
    @test all(abs.(bg_all(columns, "Ramp1/y")[columns["time"] .< t_start] .- initial) .< 1e-12)

    # Both signals follow the analytic solution on the whole recorded grid, including the
    # kink at t_start (the event pair there is continuous for both signals).
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "Ramp1/y") .- ramp.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "I1/y") .- ramp_integral.(times))) < 1e-8
end
