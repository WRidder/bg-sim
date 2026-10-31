# Golden test for `stdlib:motion/HarmonicProfile`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model: a forward move -1 -> 3 from t = 0.1 over 0.9 s (the end, 1.0 s, on the output
# grid) and a backward move 1 -> 0.4 from t = 0.37 over 0.5 s; each profile drives
# Integrators of its velocity and acceleration.
#
# Reference: with x = (t - t_start)/T and h = q_end - q_start,
#   q = q_start + h/2*(1 - cos(pi x)), v = pi h/(2T)*sin(pi x), a = pi^2 h/(2T^2)*cos(pi x).
# Checks: the outputs on the grid (1e-9), q and v continuous at every event (the
# acceleration jumps by pi^2 h/(2T^2) at both ends), the integrals of v and a, the end
# position exactly q_end, and no W206.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :MotionGolden) || include(joinpath(@__DIR__, "motion_helpers.jl"))
using Test
using .BondGraphGolden
using .MotionGolden

function _harmonic_ref(q0, q1, t0, T)
    h = q1 - q0
    function ref(t)
        (t < t0 || t >= t0 + T - 1e-12) && return (t < t0 ? q0 : q1, 0.0, 0.0)
        x = (t - t0) / T
        return (q0 + h / 2 * (1 - cos(pi * x)), pi * h / (2T) * sin(pi * x),
            pi^2 * h / (2T^2) * cos(pi * x))
    end
    return ref
end

@testset "golden: HarmonicProfile" begin
    cases = [(-1.0, 3.0, 0.1, 0.9), (1.0, 0.4, 0.37, 0.5)]
    params = [Dict("q_start" => string(c[1]), "q_end" => string(c[2]), "t_start" => string(c[3]),
        "duration" => string(c[4])) for c in cases]
    columns, result = run_profiles("HarmonicProfile", params; t_end = 1.2, points = 121)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    for (i, c) in enumerate(cases)
        @testset "case $i" begin
            q0, q1, t0, T = c
            profile_checks(columns, i, _harmonic_ref(c...); q_start = q0, q_end = q1,
                t_stop = t0 + T, switches = [t0, t0 + T], continuous_a = false)
        end
    end
    @test bg_value(columns, "P1/q", 0.55) ≈ 1.0 atol = 1e-12
    @test bg_value(columns, "P1/v", 0.55) ≈ pi * 4 / 1.8 rtol = 1e-12
    @test bg_value(columns, "P1/q", 1.0) == 3.0
end
