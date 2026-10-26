# Golden test for `stdlib:sources/Noise` (plan section 8, M2 row: the noise source),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Noise source (mean 2, std 0.5, seed 123, sample time 0.043 s) drives an
# Integrator. The sample time is deliberately not a divisor of the 0.01 s output grid, so
# the recorded rows include the clock ticks as event pairs.
#
# Reference: the deterministic Box-Muller normal sample of the block itself, on the tick
# k = floor(t / sample_time):
#   u1 = mod(sin(seed*12.9898 + k*78.233)*43758.5453, 1) + 1e-12,
#   u2 = mod(sin(seed*39.3468 + k*11.135)*24634.6345, 1),
#   y  = mean + std*sqrt(-2*log(u1))*cos(2*pi*u2),
# and the exact integral of that piecewise-constant signal. The same seed is run twice and
# must reproduce bit for bit; a different seed must change the sequence.
#
# Tolerance: rtol 1e-8 at the sample points, a 1e-8 whole-grid bound on the integral, and
# a 0.03 bound on the pure-Julia mean/std of 20000 samples (the deterministic sequence is
# standard normal to that accuracy).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Noise source" begin
    mean_value, std_value, seed, st = 2.0, 0.5, 123, 0.043

    function noise_sample(k; mean_value = mean_value, std_value = std_value, seed = seed)
        u1 = mod(sin(seed * 12.9898 + k * 78.233) * 43758.5453, 1.0) + 1.0e-12
        u2 = mod(sin(seed * 39.3468 + k * 11.135) * 24634.6345, 1.0)
        return mean_value + std_value * sqrt(-2.0 * log(u1)) *
               cos(6.283185307179586 * u2)
    end
    noise(t) = noise_sample(floor(t / st))
    function noise_area(t)
        full = floor(Int, t / st)
        total = st * sum(noise_sample(k) for k in 0:(full - 1); init = 0.0)
        return total + noise_sample(full) * (t - full * st)
    end

    function noise_model(name, seed_value)
        return bg_model(
            name,
            [
                bg_node("n1", "Noise1", bg_ref("stdlib:sources/Noise");
                    params = Dict{String,Any}("mean" => string(mean_value),
                        "std" => string(std_value), "seed" => string(seed_value),
                        "sample_time" => string(st))),
                bg_node("n2", "I1", bg_ref("stdlib:continuous/Integrator")),
            ],
            [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
            t_end = 0.5, points = 51,
        )
    end

    model = noise_model("NoiseDrivesIntegrator", seed)
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    @test flat.stats.states == 1                 # the integrator state

    for t in (0.0, 0.05, 0.1, 0.2, 0.31, 0.4, 0.5)
        @test isapprox(bg_value(columns, "Noise1/y", t), noise(t); rtol = 1e-8,
            atol = 1e-10)
        @test isapprox(bg_value(columns, "I1/y", t), noise_area(t); rtol = 1e-8,
            atol = 1e-9)
    end

    # Piecewise constant between two clock ticks (both are inside tick 1).
    @test isapprox(bg_value(columns, "Noise1/y", 0.05),
        bg_value(columns, "Noise1/y", 0.06); rtol = 1e-12)

    # The same seed repeats the run bit for bit; a different seed changes the sequence.
    columns2, result2, _ = bg_run(noise_model("NoiseDrivesIntegrator", seed))
    @test result2.status == "done"
    @test bg_all(columns, "Noise1/y") == bg_all(columns2, "Noise1/y")
    @test bg_all(columns, "time") == bg_all(columns2, "time")

    other, result3, _ = bg_run(noise_model("NoiseOtherSeed", seed + 1))
    @test result3.status == "done"
    @test abs(bg_value(other, "Noise1/y", 0.2) - noise(0.2)) > 1e-6

    # The deterministic sequence really is standard normal: check the reference formula
    # directly over many ticks (no simulator involved).
    zs = [noise_sample(k; mean_value = 0.0, std_value = 1.0) for k in 0:19999]
    m = sum(zs) / length(zs)
    s = sqrt(sum((zs .- m) .^ 2) / (length(zs) - 1))
    @test abs(m) < 0.03
    @test abs(s - 1.0) < 0.03
end
