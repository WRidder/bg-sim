# Golden test for `stdlib:motion/PolynomialProfile`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model: a forward move 0 -> 2 from t = 0.25 over 1.0 s (start and end on the output grid)
# and a backward move 0.5 -> -0.7 from t = 0.033 over 0.8 s; each profile drives Integrators
# of its velocity, acceleration and jerk.
#
# Reference: the 3-4-5 polynomial with x = (t - t_start)/T and h = q_end - q_start,
#   q = q_start + h*(10x^3 - 15x^4 + 6x^5), v = 30h/T x^2 (1 - x)^2,
#   a = 60h/T^2 x (1 - x)(1 - 2x), jerk = 60h/T^3 (1 - 6x + 6x^2).
# Checks: the outputs on the grid (1e-9), q, v and a continuous at the ends (the jerk jumps
# by 60h/T^3), the integrals of v, a and jerk, the end position exactly q_end, the peak
# velocity 1.875 h/T at the middle, the peak acceleration 10 h/(sqrt(3) T^2), no W206.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :MotionGolden) || include(joinpath(@__DIR__, "motion_helpers.jl"))
using Test
using .BondGraphGolden
using .MotionGolden

function _quintic_ref(q0, q1, t0, T)
    h = q1 - q0
    function ref(t)
        (t < t0 || t >= t0 + T - 1e-12) && return (t < t0 ? q0 : q1, 0.0, 0.0, 0.0)
        x = (t - t0) / T
        return (q0 + h * (10x^3 - 15x^4 + 6x^5), 30h / T * x^2 * (1 - x)^2,
            60h / T^2 * x * (1 - x) * (1 - 2x), 60h / T^3 * (1 - 6x + 6x^2))
    end
    return ref
end

@testset "golden: PolynomialProfile" begin
    cases = [(0.0, 2.0, 0.25, 1.0), (0.5, -0.7, 0.033, 0.8)]
    params = [Dict("q_start" => string(c[1]), "q_end" => string(c[2]), "t_start" => string(c[3]),
        "duration" => string(c[4])) for c in cases]
    columns, result = run_profiles("PolynomialProfile", params; jerk = true, t_end = 1.5, points = 151)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    for (i, c) in enumerate(cases)
        @testset "case $i" begin
            q0, q1, t0, T = c
            profile_checks(columns, i, _quintic_ref(c...); q_start = q0, q_end = q1,
                t_stop = t0 + T, switches = [t0, t0 + T], jerk = true)
        end
    end
    @test bg_value(columns, "P1/v", 0.75) ≈ 1.875 * 2.0 rtol = 1e-12
    @test bg_value(columns, "P1/q", 0.75) ≈ 1.0 atol = 1e-12
    @test maximum(columns["P1/a"]) <= 10 * 2.0 / sqrt(3) * (1 + 1e-9)
    @test bg_value(columns, "P1/q", 1.25) == 2.0
end
