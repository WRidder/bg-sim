# Golden test for `stdlib:sources/Noise` (plan section 8, M2 row: the noise source; J-EX9:
# the specified PRNG), through the real pipeline (`parse` -> `flatten` -> `lower` ->
# `simulate`).
#
# Model: a Noise source (mean 2, std 0.5, seed 123, sample time 0.043 s) drives an
# Integrator. The sample time is deliberately not a divisor of the 0.01 s output grid, so
# the recorded rows include the clock ticks as event pairs.
#
# Reference (J-EX9, spec "Seeded noise"): tick n (at t = n * 0.043 s, n >= 1) draws sample
# n - 1 of the counter-based stream, z = noise_normal(seed, n - 1); before the first tick
# z = 0. The output is y = mean + std * z, held between ticks, and the integrator holds the
# exact integral of that piecewise-constant signal. The held z is compared with `==` against
# `BGSim.bg_noise_normal`: the simulator runs the specified function itself. The same seed
# is run twice and must reproduce bit for bit; a different seed changes the sequence.
#
# The stream itself: the SplitMix64 reference vector, pinned samples (a change of the
# specification must be deliberate) and the distribution of 200 000 samples.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Noise source" begin
    mean_value, std_value, seed, st_ns = 2.0, 0.5, 123, 43_000_000
    st = st_ns / 1e9

    ticks(t) = div(round(Int64, t * 1e9), st_ns)           # ticks run up to and at t
    z(t) = (n = ticks(t); n == 0 ? 0.0 : BGSim.bg_noise_normal(seed, n - 1))
    noise(t) = mean_value + std_value * z(t)
    function noise_area(t)
        n = ticks(t)
        total = mean_value * min(t, st)                    # [0, st): z = 0
        for j in 1:(n - 1)
            total += st * noise(j * st)
        end
        n >= 1 && (total += (t - n * st) * noise(t))
        return total
    end

    function noise_model(name, seed_value)
        node = bg_node("n1", "Noise1", bg_ref("stdlib:sources/Noise");
            params = Dict{String,Any}("mean" => string(mean_value),
                "std" => string(std_value), "seed" => string(seed_value)))
        node["constants"] = Dict{String,Any}("sample_time" => st)
        return bg_model(
            name,
            [node, bg_node("n2", "I1", bg_ref("stdlib:continuous/Integrator"))],
            [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
            t_end = 0.5, points = 51,
        )
    end

    model = noise_model("NoiseDrivesIntegrator", seed)
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the integrator state
    @test length(flat.discrete) == 1             # the noise clock

    for t in (0.0, 0.03, 0.05, 0.1, 0.2, 0.31, 0.4, 0.5)
        @test bg_value(columns, "Noise1/z", t) == z(t)
        @test isapprox(bg_value(columns, "Noise1/y", t), noise(t); rtol = 1e-14)
        @test isapprox(bg_value(columns, "I1/y", t), noise_area(t); rtol = 1e-8, atol = 1e-9)
    end
    @test bg_value(columns, "Noise1/y", 0.0) == mean_value  # before the first tick
    # Piecewise constant between two clock ticks (both are inside tick 1).
    @test bg_value(columns, "Noise1/y", 0.05) == bg_value(columns, "Noise1/y", 0.08)

    # The same seed repeats the run bit for bit; a different seed changes the sequence.
    columns2, result2, _ = bg_run(noise_model("NoiseDrivesIntegrator", seed))
    @test result2.status == "done"
    @test bg_all(columns, "Noise1/y") == bg_all(columns2, "Noise1/y")
    @test bg_all(columns, "time") == bg_all(columns2, "time")

    other, result3, _ = bg_run(noise_model("NoiseOtherSeed", seed + 1))
    @test result3.status == "done"
    @test abs(bg_value(other, "Noise1/y", 0.2) - noise(0.2)) > 1e-6

    @testset "the specified stream" begin
        # SplitMix64's reference vector: the generator seeded with 0 starts
        # 0xe220a8397b1dcdaf, 0x6e789e6aa1b965f4; the key of seed 0 is its first output.
        @test BGSim.noise_mix(0x9e3779b97f4a7c15) == 0xe220a8397b1dcdaf
        @test BGSim.noise_mix(0x9e3779b97f4a7c15 * 0x02) == 0x6e789e6aa1b965f4
        # Pinned samples: changing any of these changes every noisy model.
        @test BGSim.bg_noise_uniform(1, 0) == 0.3681895156516696
        @test [BGSim.bg_noise_normal(1, k) for k in 0:2] ==
              [-0.3366522922158836, 1.5854173652844237, -1.6926925951922183]
        # Integers as doubles are the same stream; anything else is NaN.
        @test BGSim.bg_noise_normal(7.0, 3.0) == BGSim.bg_noise_normal(7, 3)
        @test BGSim.bg_noise_normal(-5, -9) == BGSim.bg_noise_normal(-5.0, -9.0)
        @test isnan(BGSim.bg_noise_normal(1.5, 0)) && isnan(BGSim.bg_noise_normal(1, Inf))
        @test isnan(BGSim.bg_noise_uniform(NaN, 0)) && isnan(BGSim.bg_noise_uniform(0, 2.0^63))
        # The extremes of the transform: u = 2^-53 and 1 - 2^-53.
        @test BGSim.noise_ppnd(0x1p-53) == -BGSim.noise_ppnd(1 - 0x1p-53)
        @test -8.3 < BGSim.noise_ppnd(0x1p-53) < -8.2
        # noise_log is a deterministic logarithm, within 2 ulp of the true one.
        for x in (0x1p-53, 1.4e-11, 0.1, 0.4999, 0.5, 0.7, 1.0)
            ref = Float64(log(big(x)))
            @test abs(BGSim.noise_log(x) - ref) <= 2 * eps(abs(ref) + floatmin())
        end

        # The distribution: 200 000 samples of two seeds, moments and tail fractions.
        zs = vcat([BGSim.bg_noise_normal(11, k) for k in 0:99_999],
            [BGSim.bg_noise_normal(12, k) for k in 0:99_999])
        n = length(zs)
        m = sum(zs) / n
        s = sqrt(sum((zs .- m) .^ 2) / (n - 1))
        @test abs(m) < 0.01                       # 4.5 sigma of the sample mean
        @test abs(s - 1.0) < 0.01
        @test abs(count(<(0), zs) / n - 0.5) < 0.005
        @test abs(count(x -> abs(x) > 1.959963984540054, zs) / n - 0.05) < 0.003
        us = [BGSim.bg_noise_uniform(3, k) for k in 0:99_999]
        @test all(u -> 0 < u < 1, us)
        @test abs(sum(us) / length(us) - 0.5) < 0.005
    end
end
