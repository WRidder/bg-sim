# Golden test for `stdlib:continuous/LeadLag` (plan section 8, M2 row: lead-lag), through
# the real pipeline.
#
# Model: k = 2, T_lead = 0.5 s, T_lag = 0.2 s, driven by a unit step at t = 0.1 s.
#
# Reference: with r = T_lead/T_lag and tau = t - 0.1, the analytic response is
#   y = k*(1 + (r - 1) * exp(-tau/T_lag)) = 2*(1 + 1.5*exp(-5*tau)),
# i.e. an immediate lead boost to k*r = 5 followed by a decay to k.
# Tolerance: rtol 1e-6 at the sampled points.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: LeadLag" begin
    k, T_lead, T_lag, t_step = 2.0, 0.5, 0.2, 0.1
    r = T_lead / T_lag
    model = bg_model(
        "LeadLagStep",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => string(t_step),
                    "initial" => "0.0", "final" => "1.0")),
            bg_node("n2", "L1", bg_ref("stdlib:continuous/LeadLag");
                params = Dict{String,Any}("k" => string(k), "T_lead" => string(T_lead),
                    "T_lag" => string(T_lag))),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1

    exact(t) = t < t_step ? 0.0 : k * (1.0 + (r - 1.0) * exp(-(t - t_step) / T_lag))
    for t in (0.0, 0.05, 0.1, 0.15, 0.25, 0.5, 1.0, 2.0)
        @test isapprox(bg_value(columns, "L1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    @test bg_value(columns, "L1/y", t_step) > k * r - 1e-6   # the lead boost at the step
end
