# Golden test for `stdlib:sources/Pulse` (plan section 8, M2 row: the pulse / square
# source), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: two Pulse instances with the same period and start time but complementary duties
# (0.25 and 0.75), each driving an Integrator. This checks both sides of the duty split.
#
# Reference: the analytic piecewise-constant pulse train.
#   y(t) = amplitude while frac((t - t_start)/period) < duty (and t >= t_start), else 0;
#   the integrator is the exact area of the high intervals up to t.
# The block computes the same train from a sinusoidal phase threshold, so its edges are
# smooth zero crossings rather than sawtooth wraps (the golden asserts that the event
# collector sees clean crossings: no W206).
#
# Tolerance: rtol 1e-6 at the sample points and a 1e-8 whole-grid bound on the integrals
# (the run itself uses reltol 1e-10, abstol 1e-12).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Pulse source" begin
    period, t_start = 0.37, 0.023
    # Chosen so that no pulse edge is a multiple of the 0.01 s output grid.
    pulse(t, amplitude, duty) =
        (t >= t_start && mod((t - t_start) / period, 1.0) < duty) ? amplitude : 0.0

    function pulse_area(t, amplitude, duty)
        total = 0.0
        k = 0
        while true
            on = t_start + k * period
            on > t && break
            off = min(on + duty * period, t)
            total += amplitude * max(0.0, off - on)
            k += 1
        end
        return total
    end

    model = bg_model(
        "PulseDrivesIntegrators",
        [
            bg_node("n1", "Pulse1", bg_ref("stdlib:sources/Pulse");
                params = Dict{String,Any}("amplitude" => "2.0",
                    "period" => string(period), "duty" => "0.25",
                    "t_start" => string(t_start))),
            bg_node("n2", "Pulse2", bg_ref("stdlib:sources/Pulse");
                params = Dict{String,Any}("amplitude" => "1.0",
                    "period" => string(period), "duty" => "0.75",
                    "t_start" => string(t_start))),
            bg_node("n3", "I1", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n4", "I2", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u"),
        ];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    @test flat.stats.states == 2                 # the two integrators

    for t in (0.0, 0.05, 0.1, 0.15, 0.25, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)
        @test isapprox(bg_value(columns, "Pulse1/y", t), pulse(t, 2.0, 0.25);
            rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "Pulse2/y", t), pulse(t, 1.0, 0.75);
            rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/y", t), pulse_area(t, 2.0, 0.25);
            rtol = 1e-6, atol = 1e-8)
        @test isapprox(bg_value(columns, "I2/y", t), pulse_area(t, 1.0, 0.75);
            rtol = 1e-6, atol = 1e-8)
    end

    # Before the start and over the high fraction, the pulse is exactly the amplitude.
    @test all(abs.(bg_all(columns, "Pulse1/y")[columns["time"] .< t_start]) .< 1e-12)
    # The area is continuous, so it matches on every recorded row (event pairs included).
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "I1/y") .- pulse_area.(times, 2.0, 0.25))) < 1e-8
    @test maximum(abs.(bg_all(columns, "I2/y") .- pulse_area.(times, 1.0, 0.75))) < 1e-8
end
