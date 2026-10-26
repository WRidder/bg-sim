# Golden test for `stdlib:sources/Chirp` (plan section 8, M2 row: the chirp source),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Chirp (2 Hz -> 8 Hz over 0.5 s) drives an Integrator, so the model has a state.
#
# Reference: the analytic linear frequency sweep.
#   phase(t) = f_start*t + (f_end - f_start)*t^2/(2*duration)   for t <= duration,
#   phase(t) = phase(duration) + f_end*(t - duration)          afterwards,
#   y(t) = sin(2*pi*phase(t)).
# The phase and its derivative are continuous at t = duration, so the chirp itself is
# continuous; only its second derivative turns off.
#
# Tolerance: rtol 1e-6 at the sample points and a 1e-8 whole-grid bound (the run itself
# uses reltol 1e-10, abstol 1e-12).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Chirp source" begin
    f_start, f_end, duration = 2.0, 8.0, 0.5
    function phase(t)
        return t <= duration ?
               f_start * t + (f_end - f_start) * t * t / (2.0 * duration) :
               f_start * duration + (f_end - f_start) * duration / 2.0 +
               f_end * (t - duration)
    end
    chirp(t) = sin(6.283185307179586 * phase(t))

    model = bg_model(
        "ChirpDrivesIntegrator",
        [
            bg_node("n1", "Chirp1", bg_ref("stdlib:sources/Chirp");
                params = Dict{String,Any}("f_start" => string(f_start),
                    "f_end" => string(f_end), "duration" => string(duration))),
            bg_node("n2", "I1", bg_ref("stdlib:continuous/Integrator")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the integrator state

    for t in (0.0, 0.1, 0.25, 0.45, 0.5, 0.6, 0.75, 0.9, 1.0)
        @test isapprox(bg_value(columns, "Chirp1/y", t), chirp(t); rtol = 1e-6,
            atol = 1e-9)
    end

    # The whole recorded grid follows the analytic chirp (event pairs included: y is
    # continuous, so both sides of the event at t = duration have the same value).
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "Chirp1/y") .- chirp.(times))) < 1e-8
end
