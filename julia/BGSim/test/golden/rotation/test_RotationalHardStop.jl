# Golden test for `stdlib:rotation/RotationalHardStop`, through the real pipeline.
#
# Model: a `SpeedSource` (gain w, driven by a Constant 1) prescribes the relative speed
# `a.f - b.f`; `b` is a `FixedShaft`. The state integrates the imposed speed,
# phi(t) = w*t, and the block's dead-zone law is (the rotational twin of HardStop)
#
#   phi > upper:  a.e = k*(phi - upper) + d*w
#   phi < lower:  a.e = k*(phi - lower) + d*w
#   otherwise:    a.e = 0,                          b.e = -a.e.
#
# Driven up, the stop is hit at t_c = upper/w; driven down, at lower/(-w). The energy the
# speed source puts in after contact is the spring energy plus the damper loss:
#   int P dt = k*(phi - upper)^2/2 + d*w^2*(t - t_c),
# checked through the recorded power at every grid point (trapezoidal integral).
# Tolerance: rtol 1e-6 against the analytic values.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const RHS_k = 2.0e3        # N*m/rad
const RHS_d = 5.0          # N*m*s/rad
const RHS_lower = -0.213   # rad
const RHS_upper = 0.313    # rad

"""The exact dead-zone law, written from the block's specification."""
function rotational_hard_stop_torque(phi, w)
    phi > RHS_upper && return RHS_k * (phi - RHS_upper) + RHS_d * w
    phi < RHS_lower && return RHS_k * (phi - RHS_lower) + RHS_d * w
    return 0.0
end

function rotational_hard_stop_model(w)
    return bg_model(
        "RotationalHardStopConstantSpeed",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "HS1", bg_ref("stdlib:rotation/RotationalHardStop");
                params = Dict{String,Any}("lower" => string(RHS_lower),
                    "upper" => string(RHS_upper), "k" => string(RHS_k), "d" => string(RHS_d))),
            bg_node("n4", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.2, points = 201,
    )
end

@testset "golden: RotationalHardStop" begin
    for w in (2.5, -2.5)
        columns, result, flat = bg_run(rotational_hard_stop_model(w))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 1
        limit = w > 0 ? RHS_upper : RHS_lower
        t_c = limit / w
        @test 0.08 < t_c < 0.13
        for t in (0.0, 0.05, 0.08, 0.14, 0.17, 0.2)
            phi = w * t
            torque = rotational_hard_stop_torque(phi, w)
            @test isapprox(bg_value(columns, "HS1/phi", t), phi; rtol = 1e-9, atol = 1e-12)
            @test isapprox(bg_value(columns, "HS1/a.e", t), torque; rtol = 1e-6, atol = 1e-9)
            @test isapprox(bg_value(columns, "HS1/b.e", t), -torque; rtol = 1e-6, atol = 1e-9)
            @test isapprox(bg_value(columns, "W1/a.e", t), -torque; rtol = 1e-6, atol = 1e-9)
        end
        # Free rotation: exactly zero torque before the stop, contact torque after it.
        @test bg_value(columns, "HS1/a.e", 0.08) == 0.0
        @test abs(bg_value(columns, "HS1/a.e", 0.14)) > 0.0
        @test sign(bg_value(columns, "HS1/a.e", 0.2)) == sign(w)

        # Energy: the integral of the power into the stop equals the stored spring energy
        # plus the damper loss, and the power into the stop is never negative here.
        times = columns["time"]
        power = bg_all(columns, "HS1/a.P") .+ bg_all(columns, "HS1/b.P")
        @test all(p -> p >= -1e-9, power)
        energy = 0.0
        for i in 2:length(times)
            energy += 0.5 * (power[i] + power[i - 1]) * (times[i] - times[i - 1])
        end
        t = times[end]
        expected = 0.5 * RHS_k * (w * t - limit)^2 + RHS_d * w^2 * (t - t_c)
        @test isapprox(energy, expected; rtol = 1e-3)
    end
end
