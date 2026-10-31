# Shared helpers of the motion-profile golden tests (TrapezoidalProfile, SCurveProfile,
# CycloidalProfile, PolynomialProfile, HarmonicProfile). Included by those test files, not
# by the golden walk (the file name does not start with `test_`).
module MotionGolden

using Test
using ..BondGraphGolden

export run_profiles, max_rate, profile_checks

"""    run_profiles(block, cases; outputs, t_end, points) -> (columns, result)

One model with an instance `P<i>` of `stdlib:motion/<block>` per entry of `cases` (its
parameter Dict, values as strings). Every derivative output drives an Integrator, so the
model has states and the integrals check the outputs against each other: `IV<i>` integrates
`v` (so IV = q - q_start), `IA<i>` integrates `a` (IA = v) and, when the block has a jerk
output, `IJ<i>` integrates `jerk` (IJ = a)."""
function run_profiles(block, cases; jerk = false, t_end, points)
    nodes, conns = Any[], Any[]
    for (i, params) in enumerate(cases)
        push!(nodes, bg_node("p$i", "P$i", bg_ref("stdlib:motion/" * block);
            params = Dict{String,Any}(params)))
        pairs = [("v", "IV"), ("a", "IA")]
        jerk && push!(pairs, ("jerk", "IJ"))
        for (out, name) in pairs
            push!(nodes, bg_node(lowercase(name) * "$i", name * "$i",
                bg_ref("stdlib:continuous/Integrator")))
            push!(conns, bg_conn("c$(name)$i", "signal", "p$i", out, lowercase(name) * "$i", "u"))
        end
    end
    columns, result, _ = bg_run(bg_model(block * "Profiles", nodes, conns;
        t_end = t_end, points = points))
    return columns, result
end

"""    max_rate(columns, id) -> Float64

The largest |Δy/Δt| of signal `id` between consecutive recorded rows. Rows closer than
1 ns (an event pair, or a grid time next to a switch one ulp away) only count when the
signal changes by more than 1e-9 there, as an infinite rate. A signal that is continuous with a derivative
bounded by B never exceeds B (the checks allow 0.1 % for a peak between grid points),
while a jump of size δ between two rows Δt apart shows up as δ/Δt, 100δ on the 0.01 s grid."""
function max_rate(columns, id)
    times = columns["time"]
    values = columns[id]
    rate = 0.0
    for k in 1:length(times) - 1
        dy = abs(values[k + 1] - values[k])
        dt = times[k + 1] - times[k]
        rate = max(rate, dt > 1.0e-9 ? dy / dt : (dy > 1.0e-9 ? Inf : 0.0))
    end
    return rate
end

"""    profile_checks(columns, i, ref; q_start, q_end, t_stop, jerk, continuous_a, tol)

The checks every profile shares, for instance `P<i>` against the analytic reference
`ref(t) -> (q, v, a[, jerk])`:
  * every output on the output grid equals the reference (right limit at a switch);
  * q and v are continuous (their recorded slopes stay within the largest v and a), and a
    too when `continuous_a` (within the largest jerk);
  * the integrals of v, a (and jerk) reproduce q - q_start, v (and a);
  * from t_stop on the position is q_end exactly and v = a = 0."""
function profile_checks(columns, i, ref; q_start, q_end, t_stop, switches = Float64[],
    jerk = false, continuous_a = true, tol = 1.0e-9, itol = 1.0e-7)
    names = jerk ? ("q", "v", "a", "jerk") : ("q", "v", "a")
    times = columns["time"]
    grid = unique(times)
    # A jumping output is compared away from its switches: a decimal switch time and the
    # grid time may round to different sides.
    away = [t for t in grid if all(abs(t - s) > 1.0e-9 for s in switches)]
    for (k, name) in enumerate(names)
        jumps = name == "jerk" || (name == "a" && !continuous_a)
        err = maximum(abs(bg_value(columns, "P$i/$name", t) - ref(t)[k])
                      for t in (jumps ? away : grid))
        @test err < tol
    end
    peak(name) = maximum(abs.(columns["P$i/$name"]))
    @test max_rate(columns, "P$i/q") <= peak("v") * (1 + 1.0e-3) + 1.0e-9
    @test max_rate(columns, "P$i/v") <= peak("a") * (1 + 1.0e-3) + 1.0e-9
    continuous_a && jerk && @test max_rate(columns, "P$i/a") <= peak("jerk") * (1 + 1.0e-3) + 1.0e-9
    q = columns["P$i/q"]
    @test maximum(abs.(columns["IV$i/y"] .- (q .- q_start))) < itol
    @test maximum(abs.(columns["IA$i/y"] .- columns["P$i/v"])) < itol
    jerk && @test maximum(abs.(columns["IJ$i/y"] .- columns["P$i/a"])) < itol
    # The rows after the end of the move (a decimal end time may round one ulp past the
    # grid time, so the grid row at the end itself can still be the last instant of the move).
    after = [k for k in eachindex(times) if times[k] > t_stop + 1.0e-9]
    @test !isempty(after)
    @test all(q[k] == q_end for k in after)
    @test all(columns["P$i/v"][k] == 0.0 for k in after)
    @test all(columns["P$i/a"][k] == 0.0 for k in after)
    return nothing
end

end # module
