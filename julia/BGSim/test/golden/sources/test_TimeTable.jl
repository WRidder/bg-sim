# Golden test for `stdlib:sources/TimeTable` (plan section 8, M2 row: the time table),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: two TimeTable instances share one uniformly sampled table; the first uses linear
# interpolation (method = 1) and the second zero-order hold (method = 0), and each drives
# an Integrator.
#
# Reference: the analytic piecewise table of the flat model.
#   * linear: the value interpolated between the samples, held at the first/last value
#     outside the table;
#   * hold: the value of the sample interval, held at the first/last value outside;
#   * the integrals are the exact areas under those two piecewise functions.
# The output grid is 0.01 s and the table spacing is 0.27 s from t = 0.033 s, so no table
# edge coincides with an output point.
#
# Tolerance: rtol 1e-6 at the sample points and a 1e-8 whole-grid bound on the integrals
# (the run itself uses reltol 1e-10, abstol 1e-12).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: TimeTable source" begin
    t_start, dt = 0.033, 0.27
    vals = [0.0, 1.0, -0.5, 2.0, 0.25, -1.0, 1.5, 0.0]
    n = length(vals) - 1                       # seven intervals, eight samples

    function table_linear(t)
        s = (t - t_start) / dt
        s <= 0.0 && return vals[1]
        s >= n && return vals[n + 1]
        i = floor(Int, s) + 1
        return vals[i] + (vals[i + 1] - vals[i]) * (s - (i - 1))
    end
    function table_hold(t)
        s = (t - t_start) / dt
        s <= 0.0 && return vals[1]
        s >= n && return vals[n + 1]
        return vals[floor(Int, s) + 1]
    end

    function table_linear_area(t)
        t <= t_start && return vals[1] * t
        total = vals[1] * t_start
        stop = min(t, t_start + n * dt)
        for k in 0:(n - 1)
            a = t_start + k * dt
            b = min(a + dt, stop)
            b <= a && break
            slope = (vals[k + 2] - vals[k + 1]) / dt
            total += vals[k + 1] * (b - a) + 0.5 * slope * (b - a)^2
        end
        t > t_start + n * dt && (total += vals[n + 1] * (t - t_start - n * dt))
        return total
    end
    function table_hold_area(t)
        t <= t_start && return vals[1] * t
        total = vals[1] * t_start
        stop = min(t, t_start + n * dt)
        for k in 0:(n - 1)
            a = t_start + k * dt
            b = min(a + dt, stop)
            b <= a && break
            total += vals[k + 1] * (b - a)
        end
        t > t_start + n * dt && (total += vals[n + 1] * (t - t_start - n * dt))
        return total
    end

    params(method) = Dict{String,Any}(
        "t_start" => string(t_start),
        "sample_time" => string(dt),
        "values" => "[" * join(vals, ", ") * "]",
        "method" => string(method),
    )

    model = bg_model(
        "TimeTableDrivesIntegrators",
        [
            bg_node("n1", "TT1", bg_ref("stdlib:sources/TimeTable"); params = params(1)),
            bg_node("n2", "TT2", bg_ref("stdlib:sources/TimeTable"); params = params(0)),
            bg_node("n3", "I1", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n4", "I2", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u"),
        ];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    @test flat.stats.states == 2                 # the two integrators

    for t in (0.0, 0.1, 0.2, 0.4, 0.55, 0.7, 0.9, 1.0)
        @test isapprox(bg_value(columns, "TT1/y", t), table_linear(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "TT2/y", t), table_hold(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/y", t), table_linear_area(t); rtol = 1e-6,
            atol = 1e-8)
        @test isapprox(bg_value(columns, "I2/y", t), table_hold_area(t); rtol = 1e-6,
            atol = 1e-8)
    end

    times = columns["time"]
    # The linear table is continuous, so it matches on every recorded row.
    @test maximum(abs.(bg_all(columns, "TT1/y") .- table_linear.(times))) < 1e-8
    # Both integrals are continuous even where the hold table jumps.
    @test maximum(abs.(bg_all(columns, "I1/y") .- table_linear_area.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "I2/y") .- table_hold_area.(times))) < 1e-8
end

# NOTE-6 regression: a fine table used to install a condition-only callback per kink
# whose condition is identically zero over a whole sample interval (`floor(u) == k`, or
# a parameter-only `method == 0`). The solver then fired at every integrator step and a
# 10 ms table reached W206 at t = 0.07 s; this run is long enough to have hit it.
@testset "golden: TimeTable fine table is free of the event flood" begin
    t_start, dt = 0.0, 0.01
    vals = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.5]
    n = length(vals) - 1

    function table_linear(t)
        s = (t - t_start) / dt
        s <= 0.0 && return vals[1]
        s >= n && return vals[n + 1]
        i = floor(Int, s) + 1
        return vals[i] + (vals[i + 1] - vals[i]) * (s - (i - 1))
    end
    function table_hold(t)
        s = (t - t_start) / dt
        s <= 0.0 && return vals[1]
        s >= n && return vals[n + 1]
        return vals[floor(Int, s) + 1]
    end
    function table_linear_area(t)
        total = 0.0
        for k in 0:(n - 1)
            a = t_start + k * dt
            b = min(a + dt, t)
            b <= a && break
            slope = (vals[k + 2] - vals[k + 1]) / dt
            total += vals[k + 1] * (b - a) + 0.5 * slope * (b - a)^2
        end
        t > t_start + n * dt && (total += vals[n + 1] * (t - t_start - n * dt))
        return total
    end
    function table_hold_area(t)
        total = 0.0
        for k in 0:(n - 1)
            a = t_start + k * dt
            b = min(a + dt, t)
            b <= a && break
            total += vals[k + 1] * (b - a)
        end
        t > t_start + n * dt && (total += vals[n + 1] * (t - t_start - n * dt))
        return total
    end

    params(method) = Dict{String,Any}(
        "t_start" => string(t_start),
        "sample_time" => string(dt),
        "values" => "[" * join(vals, ", ") * "]",
        "method" => string(method),
    )
    model = bg_model(
        "TimeTableFine",
        [
            bg_node("n1", "TT1", bg_ref("stdlib:sources/TimeTable"); params = params(1)),
            bg_node("n2", "TT2", bg_ref("stdlib:sources/TimeTable"); params = params(0)),
            bg_node("n3", "I1", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n4", "I2", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u"),
        ];
        t_end = 0.12, points = 121,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    @test flat.stats.states == 2
    # The former implementation fired 10 000 times before t = 0.07 s on this table; the
    # two instances now land on the 8 sample instants for both branches (86 firings).
    @test result.stats.events < 500
    @test result.stats.steps < 2000

    for t in (0.0, 0.005, 0.012, 0.015, 0.02, 0.04, 0.06, 0.065, 0.08, 0.12)
        @test isapprox(bg_value(columns, "TT1/y", t), table_linear(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "TT2/y", t), table_hold(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/y", t), table_linear_area(t); rtol = 1e-6,
            atol = 1e-8)
        @test isapprox(bg_value(columns, "I2/y", t), table_hold_area(t); rtol = 1e-6,
            atol = 1e-8)
    end

    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "TT1/y") .- table_linear.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "I1/y") .- table_linear_area.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "I2/y") .- table_hold_area.(times))) < 1e-8
end
