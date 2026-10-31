# Golden test for `stdlib:rotation/WormGear`, through the real pipeline.
#
# The block is an ideal gear a.f = n*b.f plus a load-dependent mesh friction at the worm,
#   s = tanh(a.f/w_eps),
#   T_loss = |b.e|/n * s * (b.e*s < 0 ? 1/eta - 1 : 1 - eta_back),   a.e = -b.e/n + T_loss,
# which makes P_b = -eta*P_a when the worm drives and P_a = -eta_back*P_b when the wheel
# drives; the friction power T_loss*a.f is never negative.
#
# Forward: a `SpeedSource` holds the worm at w, a `RotationalDamper` d on the wheel is the
# load: b.f = w/n, b.e = -d*b.f, a.e = d*b.f/(n*eta).
#
# Back-driven: the `SpeedSource` holds the wheel at w, the damper is on the worm:
# a.f = n*w, a.e = -d*a.f, b.e = n*d*a.f/eta_back, so P_a = -eta_back*P_b.
#
# Self-locking (eta_back < 0): a constant torque T_L drives the wheel, the worm is a free
# inertia. Without locking (eta_back > 0) the load accelerates both inertias at
# w_b' = T_L/(J_b + n^2*J_a/eta_back); with eta_back < 0 the gear holds the load and the
# worm creeps only at the tanh-smoothing speed w_eps*atanh(1/(1 - eta_back)).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function worm_speed_model(drive_port; n = 20.0, eta = 0.6, eta_back = 0.3, w = 5.0, d = 0.8)
    other = drive_port == "a" ? "b" : "a"
    return bg_model(
        "WormGearDriven",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "G1", bg_ref("stdlib:rotation/WormGear");
                params = Dict{String,Any}("n" => string(n), "eta" => string(eta),
                    "eta_back" => string(eta_back))),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", drive_port),
            bg_conn("c3", "wire", "n3", other, "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )
end

function worm_load_model(eta_back; n = 20.0, eta = 0.6, J_a = 1.0e-4, J_b = 0.02, T_L = 3.0)
    return bg_model(
        "WormGearLoad",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "TS1", bg_ref("stdlib:rotation/TorqueSource");
                params = Dict{String,Any}("T" => string(T_L))),
            bg_node("n3", "G1", bg_ref("stdlib:rotation/WormGear");
                params = Dict{String,Any}("n" => string(n), "eta" => string(eta),
                    "eta_back" => string(eta_back))),
            bg_node("n4", "Ja", bg_ref("stdlib:rotation/Inertia");
                params = Dict{String,Any}("J" => string(J_a))),
            bg_node("n5", "Jb", bg_ref("stdlib:rotation/Inertia");
                params = Dict{String,Any}("J" => string(J_b))),
            bg_node("n6", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n6", "a"),
            bg_conn("c3", "wire", "n2", "b", "n5", "a"),
            bg_conn("c4", "wire", "n5", "a", "n3", "b"),
            bg_conn("c5", "wire", "n5", "b", "n6", "a"),
            bg_conn("c6", "wire", "n3", "a", "n4", "a"),
            bg_conn("c7", "wire", "n4", "b", "n6", "a"),
        ];
        t_end = 0.2, points = 21,
    )
end

@testset "golden: WormGear" begin
    n = 20.0
    eta = 0.6
    eta_back = 0.3
    w = 5.0
    d = 0.8

    # Forward: the worm drives the damper on the wheel.
    columns, result, flat = bg_run(worm_speed_model("a"))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    w_b = w / n
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "G1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.f", t), w_b; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.e", t), -d * w_b; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.e", t), d * w_b / (n * eta); rtol = 1e-6)
        @test isapprox(bg_value(columns, "G1/b.P", t), -eta * bg_value(columns, "G1/a.P", t);
            rtol = 1e-6)
        @test bg_value(columns, "G1/T_loss", t) * w >= 0.0
    end

    # Back-driven with eta_back > 0: the wheel drives the damper on the worm.
    columns, result, flat = bg_run(worm_speed_model("b"))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    w_a = n * w
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "G1/a.f", t), w_a; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/a.e", t), -d * w_a; rtol = 1e-9)
        @test isapprox(bg_value(columns, "G1/b.e", t), n * d * w_a / eta_back; rtol = 1e-6)
        @test isapprox(bg_value(columns, "G1/a.P", t),
            -eta_back * bg_value(columns, "G1/b.P", t); rtol = 1e-6)
        @test bg_value(columns, "G1/a.P", t) + bg_value(columns, "G1/b.P", t) >= 0.0
    end

    # Not self-locking: the load torque on the wheel accelerates both inertias.
    J_a = 1.0e-4
    J_b = 0.02
    T_L = 3.0
    acc = T_L / (J_b + n^2 * J_a / eta_back)
    columns, result, flat = bg_run(worm_load_model(eta_back))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    for t in (0.1, 0.2)
        # The first instants pass through the tanh smoothing of the friction direction, a
        # shift of the order w_eps/n in the wheel speed.
        @test isapprox(bg_value(columns, "Jb/w", t), acc * t; rtol = 1e-3)
        @test isapprox(bg_value(columns, "Ja/w", t), n * bg_value(columns, "Jb/w", t);
            rtol = 1e-9)
    end

    # Self-locking: the same load does not move the gear beyond the creep speed. At
    # eta_back = 0 the creep has no finite limit, but the worm torque vanishes like
    # 1 - tanh(w/w_eps), so the worm speed only grows logarithmically, a few w_eps.
    for locked in (-0.2, 0.0)
        columns, result, flat = bg_run(worm_load_model(locked))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        creep = locked < 0 ? 1.0e-3 * atanh(1 / (1 - locked)) : 1.0e-2
        for t in (0.05, 0.1, 0.2)
            @test abs(bg_value(columns, "Ja/w", t)) <= 1.05 * creep
            # The wheel holds the full load torque: b.e = T_L (the torque into the gear).
            @test isapprox(bg_value(columns, "G1/b.e", t), T_L; rtol = 1e-3)
            # Both ports take power in: everything is dissipated.
            @test bg_value(columns, "G1/a.P", t) + bg_value(columns, "G1/b.P", t) >= -1e-12
        end
    end
end
