# Golden test for `stdlib:continuous/RateLimiter` (plan section 8, M2 row: rate limiter),
# through the real pipeline.
#
# Model: a Ramp u = 2t through a rate limiter with rising = 1 and falling = 0.5, state start
# 0, so y' = clamp(2t - y, -0.5, 1).
#
# Reference: while the rate is not limited (t < ln 2) the state tracks the input as a first
# order lag; from ln 2 on it rises at exactly +1:
#   y = 2t - 2 + 2*exp(-t)          for t <= ln 2,
#   y = t + ln 2 - 1                after it.
# (A ramp keeps the switching condition a smooth zero crossing; a Step would cross it as a
# jump, which the condition-only event collector sees as Zeno.)
# Tolerance: rtol 1e-6 at the sampled points.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: RateLimiter" begin
    t_knee = log(2.0)
    model = bg_model(
        "RateLimiterOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "2.0", "initial" => "0.0")),
            bg_node("n2", "R2", bg_ref("stdlib:continuous/RateLimiter");
                params = Dict{String,Any}("rising" => "1.0", "falling" => "0.5")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    @test flat.stats.states == 1

    function exact(t)
        t <= t_knee && return 2.0 * t - 2.0 + 2.0 * exp(-t)
        return t + t_knee - 1.0
    end
    for t in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
        @test isapprox(bg_value(columns, "R2/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    # In the limited stretch the slope is exactly the rising rate.
    slope = (bg_value(columns, "R2/y", 1.9) - bg_value(columns, "R2/y", 1.1)) / 0.8
    @test isapprox(slope, 1.0; rtol = 1e-6)
end
