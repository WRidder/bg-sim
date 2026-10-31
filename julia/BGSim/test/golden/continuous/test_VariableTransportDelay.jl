# Golden test for `stdlib:continuous/VariableTransportDelay`, through the real pipeline.
#
# 1. A constant delay d = 0.3 s of u = sin(2t): y = u(t - 0.3) once the line has filled
#    (initial = 0 before), within the linear interpolation error Ts^2/8 max|u''| = 5e-7.
# 2. A delay beyond max_delay (d = 2 s, max_delay = 1 s) is clamped: y = u(t - 1).
# 3. A ramped delay d = 0.1 + 0.2t: y follows u(t - d(t)) within the one-period lag of the
#    sampled delay, |u'| |d'| Ts = 4e-4.
# 4. A delayed ramp u = t through d = 0.05 is exact (the interpolation is exact for an input
#    linear between ticks), and the output is `initial` until the line has filled.
if !isdefined(@__MODULE__, :sb_node)
    include(joinpath(@__DIR__, "signal_helpers.jl"))
end
using Test

@testset "golden: VariableTransportDelay" begin
    vtd(id; params = Dict{String,Any}()) = sb_node(id, "continuous/VariableTransportDelay"; params = params)
    columns, result, _ = sb_run("VariableDelay",
        [sb_sine("S", "2.0"), sb_const("D1", "0.3"), sb_const("D2", "2.0"), sb_ramp("D3", "0.2", "0.1"),
            sb_ramp("R", "1.0", "0.0"), sb_const("D4", "0.05"),
            vtd("A"), vtd("B"), vtd("C"), vtd("E"; params = Dict("initial" => "-1.0"))],
        [("S", "y", "A", "u"), ("D1", "y", "A", "d"), ("S", "y", "B", "u"), ("D2", "y", "B", "d"),
            ("S", "y", "C", "u"), ("D3", "y", "C", "d"), ("R", "y", "E", "u"), ("D4", "y", "E", "d")];
        t_end = 2.0, points = 201)
    @test result.status == "done"
    for t in 0.0:0.01:2.0
        @test isapprox(bg_value(columns, "A/y", t), t < 0.3 ? 0.0 : sin(2(t - 0.3)); atol = 1e-6)
        @test isapprox(bg_value(columns, "B/y", t), t < 1.0 ? 0.0 : sin(2(t - 1.0)); atol = 1e-6)
        t > 0.2 && @test isapprox(bg_value(columns, "C/y", t), sin(2(t - 0.1 - 0.2t)); atol = 6e-4)
        # u - initial is delayed and initial added back: -1 until filled, then t - 0.05
        # (u(0) counts as initial, so the first period after filling blends the two).
        t < 0.0495 && @test bg_value(columns, "E/y", t) == -1.0
        t > 0.0525 && @test isapprox(bg_value(columns, "E/y", t), t - 0.05; atol = 1e-12)
    end
end
