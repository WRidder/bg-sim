# Golden test for `stdlib:motion/TrapezoidalProfile`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model: three profiles, each driving Integrators of its velocity and acceleration:
#   1. a trapezoid, q 0.5 -> 2.5 from t = 0.5 with v_max = 1, a_max = 2: T_acc = 0.5,
#      T_cruise = 1.5, so the switches 1.0, 2.5 and 3.0 s all lie on the output grid;
#   2. a backward triangle, q 1 -> -0.25 from t = 0.2 with v_max = 10, a_max = 5: v_max is
#      not reached, the peak speed is sqrt(5*1.25) = 2.5 at t = 0.7, the end at 1.2;
#   3. no move (q_start = q_end): the outputs stay at q_start, 0, 0.
#
# Reference: the closed-form profile, written here independently of the block:
#   accelerate q0 + s*a*tau^2/2, cruise at v_peak, decelerate q1 - s*a*(t_end - t)^2/2.
# Checks (MotionGolden.profile_checks): the outputs on the grid (1e-9), position and
# velocity continuous at every event, the integrals of v and a, the end position exactly
# q_end; plus the limits |v| <= v_max and |a| <= a_max, and no W206 although every switch
# of case 1 falls on an output-grid time.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :MotionGolden) || include(joinpath(@__DIR__, "motion_helpers.jl"))
using Test
using .BondGraphGolden
using .MotionGolden

function _trap_ref(q0, q1, t0, vmax, amax)
    D = abs(q1 - q0)
    s = sign(q1 - q0)
    vp = min(vmax, sqrt(amax * D))
    Ta = vp / amax
    Tc = vp > 0 ? max(D / vp - Ta, 0.0) : 0.0
    t1, t2, t3 = t0 + Ta, t0 + Ta + Tc, t0 + 2Ta + Tc
    function ref(t)
        t < t0 && return (q0, 0.0, 0.0)
        t < t1 - 1e-12 && return (q0 + s * amax * (t - t0)^2 / 2, s * amax * (t - t0), s * amax)
        t < t2 - 1e-12 && return (q0 + s * (amax * Ta^2 / 2 + vp * (t - t1)), s * vp, 0.0)
        t < t3 - 1e-12 && return (q1 - s * amax * (t3 - t)^2 / 2, s * amax * (t3 - t), -s * amax)
        return (q1, 0.0, 0.0)
    end
    return ref, t3, [t0, t1, t2, t3]
end

@testset "golden: TrapezoidalProfile" begin
    cases = [
        (0.5, 2.5, 0.5, 1.0, 2.0),
        (1.0, -0.25, 0.2, 10.0, 5.0),
        (0.75, 0.75, 0.1, 1.0, 1.0),
    ]
    params = [Dict("q_start" => string(c[1]), "q_end" => string(c[2]), "t_start" => string(c[3]),
        "v_max" => string(c[4]), "a_max" => string(c[5])) for c in cases]
    columns, result = run_profiles("TrapezoidalProfile", params; t_end = 4.0, points = 401)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)

    for (i, c) in enumerate(cases)
        @testset "case $i" begin
            ref, t_stop, sw = _trap_ref(c...)
            profile_checks(columns, i, ref; q_start = c[1], q_end = c[2], t_stop = t_stop, switches = sw,
                continuous_a = false)
            @test maximum(abs.(columns["P$i/v"])) <= c[4] * (1 + 1e-12)
            @test maximum(abs.(columns["P$i/a"])) <= c[5] * (1 + 1e-12)
        end
    end
    # Case 1 reaches v_max (a cruise), case 2 does not (a triangle with its peak at 0.7 s).
    @test bg_value(columns, "P1/v", 2.0) == 1.0
    # 1e-10: a grid row on a switch holds the values 1e-12 s after it (the run steps past a
    # switching root on a grid time, `_snap_target`), so q and v are off by v and a times 1e-12.
    @test bg_value(columns, "P1/q", 1.0) ≈ 0.75 atol = 1e-10
    @test bg_value(columns, "P1/q", 2.5) ≈ 2.25 atol = 1e-10
    @test bg_value(columns, "P2/v", 0.7) ≈ -2.5 atol = 1e-10
    @test maximum(abs.(columns["P2/v"])) ≈ 2.5 atol = 1e-12
    # The acceleration jumps at the switches, and the move ends exactly.
    @test (bg_value(columns, "P1/a", 0.99), bg_value(columns, "P1/a", 1.01)) == (2.0, 0.0)
    @test (bg_value(columns, "P1/a", 2.49), bg_value(columns, "P1/a", 2.51)) == (0.0, -2.0)
    @test bg_value(columns, "P1/q", 3.0) == 2.5
    @test bg_value(columns, "P2/q", 1.2) == -0.25
    @test all(==(0.75), columns["P3/q"])
end
