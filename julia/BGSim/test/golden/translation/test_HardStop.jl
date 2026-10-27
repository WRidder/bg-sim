# Golden test for `stdlib:translation/HardStop` (plan section 8, M2 row: Hard stop),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a `VelocitySource` (gain v, driven by a Constant 1) prescribes the relative velocity
# `a.f - b.f`; `b` is `Fixed`. In D8's Translation convention the across variable is the
# velocity `f` and the through variable the force `e`, so the state integrates the imposed
# velocity, x(t) = v*t, and the block's dead-zone law is
#
#   x > upper:  a.e = k*(x - upper) + d*v
#   x < lower:  a.e = k*(x - lower) + d*v
#   otherwise:  a.e = 0,                    b.e = -a.e.
#
# The upper limit is crossed at t = 0.0852 s (x = 0.0213 m) and the lower limit in the second
# model at the same instant (x = -0.0213 m), so the run exercises both `ifelse` branches and
# the condition-only event that lands on each switching instant. Tolerance: rtol 1e-6
# against the analytic values (the run itself is at reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const HARDSTOP_k = 5.0e4                   # N/m
const HARDSTOP_d = 200.0                   # N*s/m
const HARDSTOP_lower = -0.0213              # m
const HARDSTOP_upper = 0.0213               # m

"""The exact dead-zone law, written from the plan spec (not from recorded output)."""
function hard_stop_force(x, v;
    k = HARDSTOP_k, d = HARDSTOP_d, lower = HARDSTOP_lower, upper = HARDSTOP_upper)
    if x > upper
        return k * (x - upper) + d * v
    elseif x < lower
        return k * (x - lower) + d * v
    end
    return 0.0
end

function hard_stop_model(v)
    return bg_model(
        "HardStopConstantVelocity",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => string(v))),
            bg_node("n3", "HS1", bg_ref("stdlib:translation/HardStop");
                params = Dict{String,Any}(
                    "lower" => "-0.0213", "upper" => "0.0213",
                    "k" => "5.0e4", "d" => "200.0")),
            bg_node("n4", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.2, points = 201,
    )
end

@testset "golden: HardStop" begin
    v = 0.25                        # m/s, upward: crosses `upper` at t = 0.0852 s
    columns, result, flat = bg_run(hard_stop_model(v))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 1                 # the relative displacement x

    for t in (0.0, 0.02, 0.05, 0.08, 0.09, 0.12, 0.16, 0.2)
        x = v * t
        force = hard_stop_force(x, v)
        @test isapprox(bg_value(columns, "HS1/a.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "HS1/b.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "HS1/x", t), x; rtol = 1e-9, atol = 1e-12)
        @test isapprox(bg_value(columns, "HS1/a.e", t), force; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "HS1/b.e", t), -force; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), -force; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "F1/a.e", t), force; rtol = 1e-6, atol = 1e-9)
    end

    # Free travel: exactly zero force while x < upper, contact force after it.
    @test bg_value(columns, "HS1/a.e", 0.0) == 0.0
    @test bg_value(columns, "HS1/a.e", 0.08) == 0.0
    @test bg_value(columns, "HS1/a.e", 0.09) > 0.0
    @test 0.08 < HARDSTOP_upper / v < 0.09

    # The whole recorded grid: x is the integral of the imposed velocity and the force is
    # the analytic dead-zone law at every point. The switching instant itself is recorded
    # twice (J2.3), both limits sitting at x = upper where the `ifelse` still takes the
    # free-travel branch; the contact force starts just after it, so the pair is excluded
    # from the pointwise comparison and checked on its own.
    times = columns["time"]
    crossing = HARDSTOP_upper / v
    at_event = [abs(t - crossing) <= 1e-9 for t in times]
    @test count(at_event) == 2
    @test all(isapprox(x, HARDSTOP_upper; atol = 1e-9)
              for x in bg_all(columns, "HS1/x")[at_event])
    @test all(abs(f) <= 1e-6 for f in bg_all(columns, "HS1/a.e")[at_event])
    keep = .!at_event
    @test maximum(abs.(bg_all(columns, "HS1/x")[keep] .- v .* times[keep])) < 1e-10
    @test maximum(abs.(bg_all(columns, "HS1/a.e")[keep] .-
                      [hard_stop_force(v * t, v) for t in times[keep]])) < 1e-8

    # Lower limit: the same model driven downward crosses `lower` at t = 0.0852 s.
    down_columns, down_result, down_flat = bg_run(hard_stop_model(-v))
    @test down_result.status == "done"
    @test isempty([e for e in down_result.diagnostics if e.severity == "error"])
    @test down_flat.stats.states == 1

    for t in (0.0, 0.02, 0.05, 0.08, 0.09, 0.12, 0.16, 0.2)
        x = -v * t
        force = hard_stop_force(x, -v)
        @test isapprox(bg_value(down_columns, "HS1/a.f", t), -v; rtol = 1e-9)
        @test isapprox(bg_value(down_columns, "HS1/x", t), x; rtol = 1e-9, atol = 1e-12)
        @test isapprox(bg_value(down_columns, "HS1/a.e", t), force;
            rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(down_columns, "HS1/b.e", t), -force;
            rtol = 1e-6, atol = 1e-9)
    end

    @test bg_value(down_columns, "HS1/a.e", 0.08) == 0.0
    @test bg_value(down_columns, "HS1/a.e", 0.09) < 0.0
    @test maximum(abs.(bg_all(down_columns, "HS1/x") .- (-v) .* down_columns["time"])) <
          1e-10
end
