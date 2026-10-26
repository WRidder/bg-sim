# Golden test for `stdlib:continuous/SecondOrder` (plan section 8, M2 row: first/second
# order), through the real pipeline.
#
# Model: k = 1.5, w0 = 2 rad/s, zeta = 0.3, driven by a unit step at t = 0.1 s.
#
# Reference: the analytic underdamped step response, with tau = t - 0.1, wd = w0*sqrt(1-zeta^2)
#   y = k*(1 - exp(-zeta*w0*tau) * (cos(wd*tau) + zeta*w0/wd * sin(wd*tau))),
# and y = 0 before the step.
# Tolerance: rtol 1e-6 at the sampled points.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: SecondOrder" begin
    k, w0, zeta, t_step = 1.5, 2.0, 0.3, 0.1
    wd = w0 * sqrt(1.0 - zeta^2)
    model = bg_model(
        "SecondOrderStep",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => string(t_step),
                    "initial" => "0.0", "final" => "1.0")),
            bg_node("n2", "S2", bg_ref("stdlib:continuous/SecondOrder");
                params = Dict{String,Any}("k" => string(k), "w0" => string(w0),
                    "zeta" => string(zeta))),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 3.0, points = 301,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 2

    function exact(t)
        t < t_step && return 0.0
        tau = t - t_step
        return k * (1.0 - exp(-zeta * w0 * tau) *
                          (cos(wd * tau) + zeta * w0 / wd * sin(wd * tau)))
    end
    for t in (0.0, 0.05, 0.1, 0.3, 0.6, 1.0, 1.5, 2.0, 3.0)
        @test isapprox(bg_value(columns, "S2/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    # The peak of an underdamped response overshoots the steady state k.
    @test maximum(bg_all(columns, "S2/y")) > k + 0.1
end
