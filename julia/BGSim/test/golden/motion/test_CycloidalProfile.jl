# Golden test for `stdlib:motion/CycloidalProfile`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model: a forward move 0.2 -> 1.7 from t = 0.3 over 1.2 s (the end, 1.5 s, on the output
# grid) and a backward move 2 -> -1 from t = 0.05 over 0.65 s; each profile drives
# Integrators of its velocity, acceleration and jerk.
#
# Reference: with x = (t - t_start)/T and h = q_end - q_start,
#   q = q_start + h*(x - sin(2 pi x)/(2 pi)), v = h/T*(1 - cos(2 pi x)),
#   a = 2 pi h/T^2*sin(2 pi x), jerk = 4 pi^2 h/T^3*cos(2 pi x).
# Checks: the outputs on the grid (1e-9), q, v and a continuous at the start and the end
# (the jerk jumps by 4 pi^2 h/T^3 there), the integrals of v, a and jerk, the end position
# exactly q_end, the peak velocity 2h/T at the middle of the move, and no W206.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :MotionGolden) || include(joinpath(@__DIR__, "motion_helpers.jl"))
using Test
using .BondGraphGolden
using .MotionGolden

function _cycloidal_ref(q0, q1, t0, T)
    h = q1 - q0
    function ref(t)
        (t < t0 || t >= t0 + T - 1e-12) && return (t < t0 ? q0 : q1, 0.0, 0.0, 0.0)
        x = (t - t0) / T
        return (q0 + h * (x - sin(2pi * x) / 2pi), h / T * (1 - cos(2pi * x)),
            2pi * h / T^2 * sin(2pi * x), 4pi^2 * h / T^3 * cos(2pi * x))
    end
    return ref
end

@testset "golden: CycloidalProfile" begin
    cases = [(0.2, 1.7, 0.3, 1.2), (2.0, -1.0, 0.05, 0.65)]
    params = [Dict("q_start" => string(c[1]), "q_end" => string(c[2]), "t_start" => string(c[3]),
        "duration" => string(c[4])) for c in cases]
    columns, result = run_profiles("CycloidalProfile", params; jerk = true, t_end = 2.0, points = 201)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    for (i, c) in enumerate(cases)
        @testset "case $i" begin
            q0, q1, t0, T = c
            profile_checks(columns, i, _cycloidal_ref(c...); q_start = q0, q_end = q1,
                t_stop = t0 + T, switches = [t0, t0 + T], jerk = true)
        end
    end
    @test bg_value(columns, "P1/v", 0.9) ≈ 2 * 1.5 / 1.2 rtol = 1e-12
    @test bg_value(columns, "P1/q", 0.9) ≈ 0.95 atol = 1e-12
    @test bg_value(columns, "P1/q", 1.5) == 1.7
end
