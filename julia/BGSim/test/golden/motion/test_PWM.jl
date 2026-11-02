# Golden test for `stdlib:motion/PWM` and `stdlib:motion/PWMAverage`, through the real
# pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: five PWM generators, each output integrated, and one PWMAverage:
#   1. duty 0.3 at 10 Hz from t = 0: edges at k/10 and k/10 + 0.03, all on the 1 ms grid;
#   2. duty u = t (a Ramp) at 10 Hz: natural sampling, the output falls where the carrier
#      phase meets the duty, (t - n/10)/0.1 = t, i.e. at t = n/9 in period n;
#   3. duty 1.2 (clamped to 1), low = -1, high = 1: always high;
#   4. duty 0: always low;
#   5. duty 0.5 at 4 Hz from t = 0.25, low = 0.5, high = 2: low before 0.25, then 1/8 s
#      high, 1/8 s low;
#   PWMAverage: duty -0.2 + 1.5 t (clamped to 0..1), low = -2, high = 3.
#
# Reference: the switched waveforms written out from the carrier, and their exact
# integrals: 0.3, 0.5 (sum of n/90 for n = 1..9), 1, 0 and 1.0625 (case 5: 0.25 s at 0.5,
# then three periods of 1/8 s at 2 and 1/8 s at 0.5) over the first second. Checks: the
# outputs on the 1 ms grid away from the edges (exactly the levels), the integrals within
# 1e-8 (every edge is an exact event), and no W206 with 40 edges on output-grid times.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: PWM and PWMAverage" begin
    pwm = [
        (Dict("frequency" => "10.0"), "Constant", Dict("value" => "0.3")),
        (Dict("frequency" => "10.0"), "Ramp", Dict("slope" => "1.0")),
        (Dict("frequency" => "10.0", "low" => "-1.0", "high" => "1.0"), "Constant",
            Dict("value" => "1.2")),
        (Dict("frequency" => "10.0"), "Constant", Dict("value" => "0.0")),
        (Dict("frequency" => "4.0", "t_start" => "0.25", "low" => "0.5", "high" => "2.0"),
            "Constant", Dict("value" => "0.5")),
    ]
    nodes, conns = Any[], Any[]
    for (i, (p, src, sp)) in enumerate(pwm)
        push!(nodes, bg_node("d$i", "D$i", bg_ref("stdlib:sources/" * src);
            params = Dict{String,Any}(sp)))
        push!(nodes, bg_node("p$i", "PWM$i", bg_ref("stdlib:motion/PWM");
            params = Dict{String,Any}(p)))
        push!(nodes, bg_node("i$i", "I$i", bg_ref("stdlib:continuous/Integrator")))
        push!(conns, bg_conn("cd$i", "signal", "d$i", "y", "p$i", "u"))
        push!(conns, bg_conn("ci$i", "signal", "p$i", "y", "i$i", "u"))
    end
    push!(nodes, bg_node("da", "DA", bg_ref("stdlib:sources/Ramp");
        params = Dict{String,Any}("initial" => "-0.2", "slope" => "1.5")))
    push!(nodes, bg_node("pa", "AVG", bg_ref("stdlib:motion/PWMAverage");
        params = Dict{String,Any}("low" => "-2.0", "high" => "3.0")))
    push!(nodes, bg_node("ia", "IA", bg_ref("stdlib:continuous/Integrator")))
    push!(conns, bg_conn("cda", "signal", "da", "y", "pa", "u"))
    push!(conns, bg_conn("cia", "signal", "pa", "y", "ia", "u"))
    columns, result, _ = bg_run(bg_model("PWMGenerators", nodes, conns; t_end = 1.0, points = 1001))
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)

    frac(t, T) = (t / T) - floor(t / T + 1e-9)
    refs = [
        t -> frac(t, 0.1) < 0.3 - 1e-9 ? 1.0 : 0.0,
        t -> (t - 0.1 * floor(t / 0.1 + 1e-9)) < 0.1 * t - 1e-9 ? 1.0 : 0.0,
        t -> 1.0,
        t -> 0.0,
        t -> t < 0.25 - 1e-9 ? 0.5 : (frac(t - 0.25, 0.25) < 0.5 - 1e-9 ? 2.0 : 0.5),
    ]
    edges = [
        sort(vcat(0:0.1:1, 0.03:0.1:1)),
        sort(vcat(0:0.1:1, [n / 9 for n in 0:9])),
        Float64[],
        Float64[],
        collect(0.25:0.125:1.0),
    ]
    areas = [0.3, 0.5, 1.0, 0.0, 0.25 * 0.5 + 0.375 * 2.0 + 0.375 * 0.5]
    grid = collect(range(0.0, 1.0; length = 1001))
    for i in eachindex(pwm)
        @testset "PWM $i" begin
            away = [t for t in grid if all(abs(t - e) > 1.5e-3 for e in edges[i])]
            @test all(bg_value(columns, "PWM$i/y", t) == refs[i](t) for t in away)
            @test bg_value(columns, "I$i/y", 1.0) ≈ areas[i] atol = 1e-8
        end
    end
    # The integrator sees the switched output, so its slope is the level: the area of the
    # first period of case 1 is 0.03, of case 2's period 3 (0.3 .. 1/3) 1/30.
    @test bg_value(columns, "I1/y", 0.1) ≈ 0.03 atol = 1e-10
    @test bg_value(columns, "I2/y", 0.4) - bg_value(columns, "I2/y", 0.3) ≈ 1 / 30 atol = 1e-9

    avg(t) = -2.0 + 5.0 * clamp(-0.2 + 1.5t, 0.0, 1.0)
    # 1e-10: a grid row where the run stepped 1e-12 s past a switching root (`_snap_target`)
    # holds the values 1e-12 s later, so the ramp (slope 7.5) is off by 7.5e-12 there.
    @test maximum(abs(bg_value(columns, "AVG/y", t) - avg(t)) for t in grid) < 1e-10
    # Its integral: -2 until t = 2/15, the ramp until 0.8, then 3.
    t0, t1 = 0.2 / 1.5, 1.2 / 1.5
    @test bg_value(columns, "IA/y", 1.0) ≈ -2.0 * t0 + 0.5 * (t1 - t0) + 3.0 * (1.0 - t1) atol = 1e-8
end
