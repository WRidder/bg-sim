# Golden test for `stdlib:rotation/LossyGear` (plan section 8, M2 row: the spec's
# `LossyGear`), through the real pipeline.
#
# Model: a `SpeedSource` holds the input shaft speed and a `RotationalDamper` with `d`
# between the other shaft and a `FixedShaft` is the load. With ratio `n` and efficiency
# `eta` the block gives `a.f = n*b.f` and `b.e = -n*a.e*K`, where `K = eta` when power enters
# at a and `1/eta` when it enters at b.
#
# Driven from a (damper on b): b.f = w/n, a.e = +d*b.f/(n*eta), b.e = -d*b.f, so the
# mechanical output is exactly eta times the input: P_b = -eta*P_a.
#
# Back-driven (damper on a): a.f = n*w, a.e = -d*a.f, b.e = n*d*a.f/eta, so the input at b
# must supply P_b = -P_a/eta.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function lossy_gear_model(drive_port)
    # drive_port = "a": speed source on a, damper on b (forward).
    # drive_port = "b": speed source on b, damper on a (back-driven).
    w = 3.0
    d = 0.5
    n = 2.0
    eta = 0.9
    return bg_model(
        "LossyGearDriven",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "G1", bg_ref("stdlib:rotation/LossyGear");
                params = Dict{String,Any}("n" => string(n), "eta" => string(eta))),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        drive_port == "a" ? [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ] : [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "b"),
            bg_conn("c3", "wire", "n3", "a", "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: LossyGear" begin
    w = 3.0
    d = 0.5
    n = 2.0
    eta = 0.9

    # Forward: power enters at a, the output is eta * input.
    columns, result, flat = bg_run(lossy_gear_model("a"))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    w_out = w / n
    torque_out = d * w_out
    torque_in = torque_out / (n * eta)
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "G1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.f", t), w_out; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.e", t), torque_in; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.e", t), -torque_out; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.e", t), -torque_in; rtol = 1e-9)
        # Damper on b: it absorbs the transmitted torque at the output speed.
        @test isapprox(bg_value(columns, "D1/a.e", t), torque_out; rtol = 1e-9)
        # P_a is the input, P_b the output, and P_b = -eta*P_a.
        @test isapprox(bg_value(columns, "G1/a.P", t), torque_in * w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.P", t), -torque_out * w_out; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.P", t) + bg_value(columns, "G1/b.P", t),
            (1.0 - eta) * torque_in * w; rtol = 1e-9)
    end

    # Back-driven: the damper is on a, so the input at b must pay 1/eta.
    columns, result, flat = bg_run(lossy_gear_model("b"))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    w_a = n * w
    torque_load = d * w_a
    torque_in = n * torque_load / eta
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "G1/a.f", t), w_a; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.e", t), -torque_load; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.e", t), torque_in; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.P", t), -torque_load * w_a; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.P", t), torque_in * w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.P", t) + bg_value(columns, "G1/b.P", t),
            (1.0 / eta - 1.0) * torque_load * w_a; rtol = 1e-9)
    end
end
