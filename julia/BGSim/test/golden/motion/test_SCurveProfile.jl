# Golden test for `stdlib:motion/SCurveProfile`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model: four jerk-limited moves, each driving Integrators of its velocity, acceleration
# and jerk, one per regime of the seven-segment profile:
#   1. both limits reached: 0 -> 4 from t = 0.25, v_max = 1, a_max = 2, j_max = 8. The jerk
#      phases last a_max/j_max = 0.25 s, the acceleration 0.75 s and the cruise 3.25 s, so
#      the seven switches 0.5, 0.75, 1.0, 4.25, 4.5, 4.75 and 5.0 s lie on the output grid;
#   2. a_max reached, v_max not: 0 -> 0.5 (no cruise, the peak speed is below v_max);
#   3. neither limit reached, backwards: 0.3 -> 0.2 (only the four jerk phases);
#   4. v_max reached but a_max not (v_max*j_max < a_max^2): 1 -> 2 with v_max = 0.25.
#
# Reference: the profile integrated from its jerk. The test computes the segment durations
# from the limits on its own (Biagiotti and Melchiorri 3.4: the jerk time T_j, the
# acceleration time T_a and the cruise T_v, by the case analysis written out below) and
# integrates the piecewise-constant jerk exactly, segment by segment. Checks: the outputs on
# the grid (1e-9), q, v and a continuous at every event, the integrals of v, a and jerk, the
# end position exactly q_end, |v| <= v_max, |a| <= a_max, |jerk| in {0, j_max}, and no
# W206 although every switch of case 1 lies on the output grid.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :MotionGolden) || include(joinpath(@__DIR__, "motion_helpers.jl"))
using Test
using .BondGraphGolden
using .MotionGolden

# The segment durations of a rest-to-rest S-curve over the distance D, by cases.
function _scurve_times(D, v, a, j)
    # The cruise exists when D covers the acceleration to v and back.
    if v * j >= a^2
        Tj, Ta = a / j, a / j + v / a          # a_max reached on the way to v_max
    else
        Tj = sqrt(v / j); Ta = 2Tj             # a triangle of acceleration
    end
    D >= v * Ta && return (Tj, Ta, D / v - Ta)
    # No cruise: first try with a_max reached, else a pure jerk profile.
    Tj = a / j
    Ta = (Tj + sqrt(Tj^2 + 4D / a)) / 2
    Ta >= 2Tj && return (Tj, Ta, 0.0)
    Tj = cbrt(D / (2j))
    return (Tj, 2Tj, 0.0)
end

function _scurve_ref(q0, q1, t0, v, a, j)
    D = abs(q1 - q0)
    s = sign(q1 - q0)
    Tj, Ta, Tv = _scurve_times(D, v, a, j)
    # The jerk of the seven segments and their durations.
    jerks = (j, 0.0, -j, 0.0, -j, 0.0, j)
    durs = (Tj, Ta - 2Tj, Tj, Tv, Tj, Ta - 2Tj, Tj)
    # The state (q, v, a) at the start of every segment, integrated exactly.
    starts = Vector{NTuple{3,Float64}}(undef, 8)
    starts[1] = (0.0, 0.0, 0.0)
    for k in 1:7
        p, w, c = starts[k]
        T, J = durs[k], jerks[k]
        starts[k + 1] = (p + w * T + c * T^2 / 2 + J * T^3 / 6, w + c * T + J * T^2 / 2, c + J * T)
    end
    edges = t0 .+ cumsum(collect(durs))
    function ref(t)
        t < t0 && return (q0, 0.0, 0.0, 0.0)
        t >= edges[7] - 1e-12 && return (q1, 0.0, 0.0, 0.0)
        k = findfirst(e -> t < e - 1e-12, edges)
        tk = k == 1 ? t0 : edges[k - 1]
        p, w, c = starts[k]
        J = jerks[k]
        x = t - tk
        return (q0 + s * (p + w * x + c * x^2 / 2 + J * x^3 / 6), s * (w + c * x + J * x^2 / 2),
            s * (c + J * x), s * J)
    end
    return ref, edges[7], vcat([t0], edges), starts[8][1], Tj, Ta, Tv
end

@testset "golden: SCurveProfile" begin
    cases = [
        (0.0, 4.0, 0.25, 1.0, 2.0, 8.0),
        (0.0, 0.5, 0.1, 1.0, 2.0, 8.0),
        (0.3, 0.2, 0.05, 1.0, 2.0, 8.0),
        (1.0, 2.0, 0.0, 0.25, 2.0, 8.0),
    ]
    params = [Dict("q_start" => string(c[1]), "q_end" => string(c[2]), "t_start" => string(c[3]),
        "v_max" => string(c[4]), "a_max" => string(c[5]), "j_max" => string(c[6])) for c in cases]
    columns, result = run_profiles("SCurveProfile", params; jerk = true, t_end = 5.5, points = 551)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)

    for (i, c) in enumerate(cases)
        @testset "case $i" begin
            ref, t_stop, sw, dist, Tj, Ta, Tv = _scurve_ref(c...)
            # The reference itself covers exactly the distance.
            @test dist ≈ abs(c[2] - c[1]) rtol = 1e-12
            profile_checks(columns, i, ref; q_start = c[1], q_end = c[2], t_stop = t_stop,
                switches = sw, jerk = true)
            @test maximum(abs.(columns["P$i/v"])) <= c[4] * (1 + 1e-12)
            @test maximum(abs.(columns["P$i/a"])) <= c[5] * (1 + 1e-12)
            @test all(x -> x == 0.0 || abs(x) == c[6], columns["P$i/jerk"])
        end
    end
    # The regimes: case 1 cruises at v_max with a_max, case 2 reaches a_max only, case 3
    # neither, case 4 v_max only.
    _, _, _, _, Tj1, Ta1, Tv1 = _scurve_ref(cases[1]...)
    @test (Tj1, Ta1, Tv1) == (0.25, 0.75, 3.25)
    @test bg_value(columns, "P1/v", 2.0) == 1.0
    @test bg_value(columns, "P1/a", 0.6) == 2.0
    @test bg_value(columns, "P1/q", 5.0) == 4.0
    @test maximum(columns["P2/a"]) ≈ 2.0 atol = 1e-12
    @test maximum(columns["P2/v"]) < 1.0
    @test maximum(abs.(columns["P3/a"])) < 2.0
    @test maximum(abs.(columns["P3/v"])) < 1.0
    @test maximum(columns["P4/v"]) ≈ 0.25 atol = 1e-12
    @test maximum(columns["P4/a"]) < 2.0
end
