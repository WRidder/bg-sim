# Golden test for the random sources `stdlib:sources/UniformNoise`, `BandLimitedWhiteNoise`,
# `PRBS` and `RandomWalk`, through the real pipeline.
#
# Model: one instance of each, each with its own seed and a sample time that does not
# divide the 0.01 s output grid (so the clock ticks are event rows), driving an Integrator.
#
# Reference (spec "Seeded noise and delay"): tick n (at t = n*Ts, n >= 1) draws sample n - 1
# of the counter-based stream; the held variable is compared with `==` against the
# specification functions `BGSim.bg_noise_uniform` / `bg_noise_normal`, because the
# simulator runs exactly those. The outputs follow from the held values; the integrals are
# the exact areas of the piecewise-constant outputs. The same seeds repeat the run bit for
# bit, a different seed changes it, and the sequences have the intended distributions.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: random sources" begin
    t_end = 0.5
    # name, block, parameters, sample time in ns, held variable, held value after tick n,
    # output from the held value.
    walk(n) = (w = 0.0; for i in 0:n - 1; w = w + 0.05 * BGSim.bg_noise_normal(24, i); end; w)
    sources = [
        ("U", "UniformNoise", Dict("y_min" => "-2.0", "y_max" => "3.0", "seed" => "21"),
            43_000_000, "u", n -> n == 0 ? 0.5 : BGSim.bg_noise_uniform(21, n - 1),
            u -> -2.0 + (3.0 - -2.0) * u),
        ("W", "BandLimitedWhiteNoise", Dict("noise_power" => "0.02", "seed" => "22"),
            7_000_000, "z", n -> n == 0 ? 0.0 : BGSim.bg_noise_normal(22, n - 1),
            z -> sqrt(0.02 / 0.007) * z),
        ("P", "PRBS", Dict("amplitude" => "1.5", "offset" => "0.5", "bit_ticks" => "3",
                "seed" => "23"),
            13_000_000, "s",
            n -> n == 0 ? 0.0 : (BGSim.bg_noise_uniform(23, div(n - 1, 3)) < 0.5 ? -1.0 : 1.0),
            s -> 0.5 + 1.5 * s),
        ("R", "RandomWalk", Dict("step_std" => "0.05", "initial" => "1.0", "seed" => "24"),
            9_000_000, "w", walk, w -> 1.0 + w),
    ]

    function model(name; seed_shift = 0)
        nodes, conns = Any[], Any[]
        for (i, (label, block, params, ts_ns, _, _, _)) in enumerate(sources)
            p = Dict{String,Any}(params)
            p["seed"] = string(parse(Int, p["seed"]) + seed_shift)
            node = bg_node("s$i", label, bg_ref("stdlib:sources/" * block); params = p)
            node["constants"] = Dict{String,Any}("sample_time" => ts_ns / 1e9)
            push!(nodes, node)
            push!(nodes, bg_node("i$i", "I$i", bg_ref("stdlib:continuous/Integrator")))
            push!(conns, bg_conn("c$i", "signal", "s$i", "y", "i$i", "u"))
        end
        return bg_model(name, nodes, conns; t_end = t_end, points = 51)
    end

    columns, result, flat = bg_run(model("RandomSources"))
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W216", result.diagnostics)       # four different seeds
    @test length(flat.discrete) == 4                            # one clock per source

    times = columns["time"]
    for (i, (label, _, _, ts_ns, var, held, out)) in enumerate(sources)
        @testset "$label" begin
            st = ts_ns / 1e9
            ticks(t) = div(round(Int64, t * 1e9), ts_ns)
            for t in range(0.0, t_end; length = 51)
                @test bg_value(columns, "$label/$var", t) == held(ticks(t))
                @test bg_value(columns, "$label/y", t) == out(held(ticks(t)))
            end
            # Piecewise constant: the integral is the exact area of the held outputs.
            function area(t)
                n = ticks(t)
                total = out(held(0)) * min(t, st)
                for j in 1:n - 1
                    total += st * out(held(j))
                end
                n >= 1 && (total += (t - n * st) * out(held(n)))
                return total
            end
            @test maximum(abs.(bg_all(columns, "I$i/y") .- area.(times))) < 1e-9
        end
    end
    # PRBS takes only its two levels after the first tick (the event row at 0.013 also
    # holds the left limit, the offset).
    p = bg_all(columns, "P/y")[times .> 0.013]
    @test all(y -> y == 2.0 || y == -1.0, p)

    # The same seeds repeat the run bit for bit; other seeds change every source.
    again, _, _ = bg_run(model("RandomSources"))
    other, _, _ = bg_run(model("RandomSourcesOther"; seed_shift = 100))
    for (label, _, _, _, _, _, _) in sources
        @test bg_all(again, "$label/y") == bg_all(columns, "$label/y")
        @test bg_all(other, "$label/y") != bg_all(columns, "$label/y")
    end

    @testset "distributions" begin
        n = 100_000
        us = [BGSim.bg_noise_uniform(21, k) for k in 0:n - 1]
        @test all(u -> 0 < u < 1, us)
        @test abs(sum(us) / n - 0.5) < 0.005
        @test abs(sum((us .- 0.5) .^ 2) / n - 1 / 12) < 0.002
        bits = [BGSim.bg_noise_uniform(23, k) < 0.5 for k in 0:n - 1]
        @test abs(count(bits) / n - 0.5) < 0.005                  # a fair coin
        @test abs(count(bits[2:end] .== bits[1:end - 1]) / (n - 1) - 0.5) < 0.005  # no run bias
        # The band-limited white noise: variance noise_power / sample_time.
        zs = [sqrt(0.02 / 0.007) * BGSim.bg_noise_normal(22, k) for k in 0:n - 1]
        @test abs(sum(zs .^ 2) / n / (0.02 / 0.007) - 1) < 0.02
        # The random walk after m steps has variance m * step_std^2 (over 400 walks).
        m = 250
        ends = [sum(0.05 * BGSim.bg_noise_normal(1000 + s, i) for i in 0:m - 1) for s in 1:400]
        @test abs(sum(ends .^ 2) / 400 / (m * 0.05^2) - 1) < 0.25
    end
end
