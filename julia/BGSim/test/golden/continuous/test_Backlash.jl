# Golden test for `stdlib:continuous/Backlash`, through the real pipeline.
#
# Reference: the ideal backlash y' = clamp(y, u - w/2, u + w/2), evaluated on a 1 us grid
# (the play operator of the input). The block updates its held position every
# sample_period = 1 ms and clamps it against the input continuously, so its output follows
# the engaged input exactly and differs from the ideal one only after a reversal, by the
# input's travel since the last tick: at most |u''| Ts^2 / 2 = 2e-6 for u = sin(2t).
# The initial output is `initial`, clamped into u(0) -/+ w/2.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

function _ideal_backlash(u, w, y0, t_end; h = 1.0e-6)
    times = 0.0:h:t_end
    y = clamp(y0, u(0.0) - w / 2, u(0.0) + w / 2)
    out = Dict{Int,Float64}()
    for (k, t) in enumerate(times)
        y = clamp(y, u(t) - w / 2, u(t) + w / 2)
        k % 10000 == 1 && (out[round(Int, t * 100)] = y)   # every 0.01 s
    end
    return out
end

@testset "golden: Backlash" begin
    columns, result, _ = sb_run("BacklashSine",
        [sb_sine("S", "2.0"), sb_node("B", "continuous/Backlash"; params = Dict("width" => "0.5")),
            sb_node("B2", "continuous/Backlash"; params = Dict("width" => "0.5", "initial" => "0.2")),
            sb_node("B3", "continuous/Backlash"; params = Dict("width" => "0.5", "initial" => "0.9"))],
        [("S", "y", "B", "u"), ("S", "y", "B2", "u"), ("S", "y", "B3", "u")]; t_end = 5.0, points = 501)
    @test result.status == "done"
    ref = _ideal_backlash(t -> sin(2t), 0.5, 0.0, 5.0)
    ref2 = _ideal_backlash(t -> sin(2t), 0.5, 0.2, 5.0)
    for k in 0:500
        t = k / 100
        @test isapprox(bg_value(columns, "B/y", t), ref[k]; atol = 3e-6)
        @test isapprox(bg_value(columns, "B2/y", t), ref2[k]; atol = 3e-6)
    end
    # Hand values: engaged on the rise, held at the top, engaged on the fall.
    @test isapprox(bg_value(columns, "B/y", 0.5), sin(1.0) - 0.25; atol = 1e-12)
    @test isapprox(bg_value(columns, "B/y", 0.9), 0.75; atol = 3e-6)
    @test isapprox(bg_value(columns, "B/y", 2.0), sin(4.0) + 0.25; atol = 1e-12)
    # initial = 0.9 is clamped to u(0) + w/2 = 0.25 (until the first tick it is clamped
    # against the moving input, so B3 rides on u + w/2 for one sample period).
    @test bg_value(columns, "B3/y", 0.0) == 0.25
    @test bg_value(columns, "B2/y", 0.2) == 0.2   # held inside the band
end
