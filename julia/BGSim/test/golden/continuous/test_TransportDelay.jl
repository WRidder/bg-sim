# Golden test for `stdlib:continuous/TransportDelay` (J-EX9), through the real pipeline
# (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Semantics: the input is stored at every tick of `sample_period` (a ring of
# delay_time / sample_period - 1 slots plus the two samples around t - delay_time) and the
# output interpolates linearly between the stored samples at t - delay_time; until the line
# has filled it is `initial`, which also stands for the input at t = 0.
#
# 1. Open loop: a unit ramp (u(0) = 0 = initial) through a 50 ms delay. The ramp is linear
#    between ticks, so the interpolation is exact: y(t) = max(0, t - 0.05) to rounding.
# 2. Closed loop, the delay differential equation x' = -x(t - 0.5), x = 1 for t <= 0
#    (an Integrator with x(0) = 1, the delay with initial 1, a gain of -1). The method of
#    steps gives x = 1 - t on [0, 0.5], 0.5 - s + s^2/2 (s = t - 0.5) on [0.5, 1] and
#    0.125 - (s/2 - s^2/2 + s^3/6) (s = t - 1) on [1, 1.5]. The interpolation error is at
#    most sample_period^2/8 * max|x''| = 1.25e-7 per unit time, so 1e-6 is the bound.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _td_node(id, name; delay_time, sample_period = 1.0e-3, initial = 0.0)
    node = bg_node(id, name, bg_ref("stdlib:continuous/TransportDelay");
        params = Dict{String,Any}("initial" => string(initial)))
    node["constants"] = Dict{String,Any}("delay_time" => delay_time,
        "sample_period" => sample_period)
    return node
end

@testset "golden: TransportDelay" begin
    @testset "a ramp is delayed exactly" begin
        model = bg_model("TransportDelayRamp",
            [bg_node("n1", "R", bg_ref("stdlib:sources/Ramp")),
                _td_node("n2", "TD"; delay_time = 0.05),
                bg_node("n3", "I", bg_ref("stdlib:continuous/Integrator"))],
            [bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "signal", "n2", "y", "n3", "u")];
            t_end = 0.2, points = 201)
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        @test length(flat.discrete) == 1
        for t in (0.0, 0.01, 0.0499, 0.05, 0.0505, 0.051, 0.0773, 0.1, 0.2)
            haskey(columns, "TD/y") || break
            i = argmin(abs.(columns["time"] .- t))
            tt = columns["time"][i]
            @test isapprox(columns["TD/y"][i], max(0.0, tt - 0.05); atol = 1e-12)
        end
        # The integral of the delayed ramp: (t - 0.05)^2 / 2.
        @test isapprox(bg_value(columns, "I/y", 0.2), 0.15^2 / 2; atol = 1e-9)
    end

    @testset "the delay differential equation x' = -x(t - 0.5)" begin
        model = bg_model("TransportDelayDDE",
            [bg_node("n1", "I", bg_ref("stdlib:continuous/Integrator");
                    starts = Dict{String,Any}("x" => "1.0")),
                _td_node("n2", "TD"; delay_time = 0.5, initial = 1.0),
                bg_node("n3", "G", bg_ref("stdlib:continuous/Gain");
                    params = Dict{String,Any}("k" => "-1.0"))],
            [bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "signal", "n2", "y", "n3", "u"),
                bg_conn("c3", "signal", "n3", "y", "n1", "u")];
            t_end = 1.5, points = 151)
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        function exact(t)
            t <= 0.5 && return 1.0 - t
            if t <= 1.0
                s = t - 0.5
                return 0.5 - s + s^2 / 2
            end
            s = t - 1.0
            return 0.125 - (s / 2 - s^2 / 2 + s^3 / 6)
        end
        worst = 0.0
        for t in 0.0:0.01:1.5
            worst = max(worst, abs(bg_value(columns, "I/y", t) - exact(t)))
        end
        @test worst < 1.0e-6
        @test isapprox(bg_value(columns, "I/y", 1.5), -1 / 48; atol = 1e-6)
    end
end
