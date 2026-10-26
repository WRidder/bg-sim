# Golden test for `stdlib:continuous/FirstOrder` (plan section 8, M2 row: first/second
# order), through the real pipeline.
#
# Model: k = 1.5, tau = 0.4 s, driven by a Step from 0 to 2 at t = 0.1 s.
#
# Reference: the analytic first-order step response
#   y(t) = 0 for t < 0.1, and k*2*(1 - exp(-(t-0.1)/tau)) after it.
# Tolerance: rtol 1e-6 at the sampled points.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: FirstOrder" begin
    k, tau, t_step, amp = 1.5, 0.4, 0.1, 2.0
    model = bg_model(
        "FirstOrderStep",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => string(t_step),
                    "initial" => "0.0", "final" => string(amp))),
            bg_node("n2", "F1", bg_ref("stdlib:continuous/FirstOrder");
                params = Dict{String,Any}("k" => string(k), "tau" => string(tau))),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1

    exact(t) = t < t_step ? 0.0 : k * amp * (1.0 - exp(-(t - t_step) / tau))
    for t in (0.0, 0.05, 0.1, 0.2, 0.5, 0.9, 1.4, 2.0)
        @test isapprox(bg_value(columns, "F1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
end
