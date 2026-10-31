# Golden test for `stdlib:converters/HydraulicMotor`, through the real pipeline.
#
# 1. Static: a `SpeedSource` holds the shaft at w between two `Tank`s (inlet a at p_a,
#    outlet b at p_b). With dp = p_a - p_b:
#      Q = D*w + K_leak*dp,                            K_leak = D*w_nom*(1 - eta_v)/(eta_v*p_nom),
#      T = D*dp - K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr),    K_fr = D*(1 - eta_m),
#    the delivered torque T (shaft.e = -T). Checks the law, the efficiencies at the nominal
#    point, P_loss >= 0 in every quadrant and the port power balance.
# 2. Dynamic: the ideal motor (eta_v = eta_m = 1) between a 100 bar supply and a 1 bar tank
#    accelerates an `Inertia` J from rest: J*dw/dt = D*dp, so w(t) = D*dp*t/J and the
#    consumed flow is Q(t) = D*w(t); the hydraulic work dp*int(Q) equals the kinetic
#    energy J*w^2/2.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _hm_law(w, dp; D = 1.6e-6, eta_v = 0.95, eta_m = 0.9, p_nom = 1.0e7,
    w_nom = 157.0, p_tr = 1.0e5, w_tr = 1.0)
    K_leak = D * w_nom * (1 - eta_v) / (eta_v * p_nom)
    K_fr = D * (1 - eta_m)
    Q = D * w + K_leak * dp
    T = D * dp - K_fr * dp * tanh(dp / p_tr) * tanh(w / w_tr)
    return Q, T, K_leak * dp^2 + K_fr * dp * tanh(dp / p_tr) * tanh(w / w_tr) * w
end

function _hm_static_model(w, p_a, p_b)
    return bg_model(
        "MotorBetweenTanks",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "M1", bg_ref("stdlib:converters/HydraulicMotor")),
            bg_node("n4", "TA", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_a))),
            bg_node("n5", "TB", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_b))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "shaft"),
            bg_conn("c3", "wire", "n4", "a", "n3", "a"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 3,
    )
end

@testset "golden: HydraulicMotor" begin
    @testset "nominal point" begin
        columns, result, flat = bg_run(_hm_static_model(157.0, 1.01e7, 1.0e5))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        dp = 1.0e7
        Q = bg_value(columns, "M1/Q", 0.01)
        T = bg_value(columns, "M1/T", 0.01)
        @test isapprox(1.6e-6 * 157.0 / Q, 0.95; rtol = 1e-9)        # volumetric
        @test isapprox(T / (1.6e-6 * dp), 0.9; rtol = 1e-9)           # hydromechanical
        @test isapprox(T * 157.0 / (dp * Q), 0.95 * 0.9; rtol = 1e-9) # overall
        @test isapprox(bg_value(columns, "M1/shaft.e", 0.01), -T; rtol = 1e-12)
    end

    @testset "w = $w, p_a = $p_a, p_b = $p_b" for (w, p_a, p_b) in (
        (100.0, 1.5e7, 1.0e5),     # motoring
        (-100.0, 1.5e7, 1.0e5),    # driven backwards against the pressure (pumping)
        (100.0, 1.0e5, 1.5e7),     # overrunning load
        (0.4, 3.0e6, 1.0e5),       # inside the friction speed band
        (0.0, 1.0e5, 1.0e5),       # standstill
    )
        dp = p_a - p_b
        Q, T, P_loss = _hm_law(w, dp)
        columns, result, _ = bg_run(_hm_static_model(w, p_a, p_b))
        @test result.status == "done"
        @test isapprox(bg_value(columns, "M1/Q", 0.01), Q; rtol = 1e-9, atol = 1e-18)
        @test isapprox(bg_value(columns, "M1/T", 0.01), T; rtol = 1e-9, atol = 1e-12)
        @test isapprox(bg_value(columns, "M1/P_loss", 0.01), P_loss; rtol = 1e-9, atol = 1e-12)
        @test P_loss >= 0
        P_in = bg_value(columns, "M1/shaft.P", 0.01) + bg_value(columns, "M1/a.P", 0.01) +
               bg_value(columns, "M1/b.P", 0.01)
        @test isapprox(P_in, P_loss; rtol = 1e-7, atol = 1e-9)
    end

    @testset "ideal motor accelerates an inertia" begin
        D, J, p_s, p_t = 2.0e-6, 0.05, 1.0e7, 1.0e5
        dp = p_s - p_t
        model = bg_model(
            "MotorSpinsInertia",
            [
                bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0")),
                bg_node("n2", "PS", bg_ref("stdlib:hydraulic/PressureSource");
                    params = Dict{String,Any}("p" => string(p_s))),
                bg_node("n3", "M1", bg_ref("stdlib:converters/HydraulicMotor");
                    params = Dict{String,Any}("D" => string(D), "eta_v" => "1.0",
                        "eta_m" => "1.0")),
                bg_node("n4", "TK", bg_ref("stdlib:hydraulic/Tank");
                    params = Dict{String,Any}("p" => string(p_t))),
                bg_node("n5", "J1", bg_ref("stdlib:rotation/Inertia");
                    params = Dict{String,Any}("J" => string(J))),
                bg_node("n6", "G1", bg_ref("stdlib:rotation/FixedShaft")),
            ],
            [
                bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "wire", "n2", "a", "n3", "a"),
                bg_conn("c3", "wire", "n3", "b", "n4", "a"),
                bg_conn("c4", "wire", "n3", "shaft", "n5", "a"),
                bg_conn("c5", "wire", "n5", "b", "n6", "a"),
            ];
            t_end = 0.1, points = 11,
        )
        columns, result, _ = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        alpha = D * dp / J
        for t in (0.0, 0.03, 0.05, 0.1)
            w = alpha * t
            @test isapprox(bg_value(columns, "M1/w", t), w; rtol = 1e-8, atol = 1e-10)
            @test isapprox(bg_value(columns, "M1/Q", t), D * w; rtol = 1e-8, atol = 1e-16)
            @test isapprox(bg_value(columns, "M1/T", t), D * dp; rtol = 1e-10)
            # The hydraulic work dp*int(Q dt) = dp*D*alpha*t^2/2 is the kinetic energy.
            @test isapprox(dp * D * alpha * t^2 / 2, J * w^2 / 2; rtol = 1e-12)
            @test isapprox(bg_value(columns, "J1/w", t), w; rtol = 1e-8, atol = 1e-10)
        end
    end
end
