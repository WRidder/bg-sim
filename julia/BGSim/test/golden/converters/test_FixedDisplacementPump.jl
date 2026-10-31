# Golden test for `stdlib:converters/FixedDisplacementPump`, through the real pipeline.
#
# Model: a `SpeedSource` turns the shaft at w; a `Tank` holds the suction a at p_a and a
# second one the delivery b at p_b. With dp = p_b - p_a the block's law is
#
#   Q = D*w - K_leak*dp,                       K_leak = D*w_nom*(1 - eta_v)/p_nom,
#   T = D*dp + K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr),  K_fr = D*(1 - eta_m)/eta_m.
#
# Checks: the flow and torque against the analytic law (rtol 1e-9); the ideal pump
# (eta_v = eta_m = 1) is lossless, P_mech = T*w = dp*Q; the lossy pump meets its two
# efficiencies at the nominal point and dissipates P_loss >= 0 in all four quadrants, and
# the port powers balance: shaft.P + a.P + b.P = P_loss.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _fdp_law(w, dp; D = 1.6e-6, eta_v = 0.95, eta_m = 0.9, p_nom = 1.0e7,
    w_nom = 157.0, p_tr = 1.0e5, w_tr = 1.0)
    K_leak = D * w_nom * (1 - eta_v) / p_nom
    K_fr = D * (1 - eta_m) / eta_m
    Q = D * w - K_leak * dp
    T = D * dp + K_fr * dp * tanh(dp / p_tr) * tanh(w / w_tr)
    return Q, T, K_leak * dp^2 + (T - D * dp) * w
end

function _fdp_model(w, p_a, p_b, params)
    return bg_model(
        "FixedPumpBetweenTanks",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "P1", bg_ref("stdlib:converters/FixedDisplacementPump");
                params = Dict{String,Any}(params)),
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

@testset "golden: FixedDisplacementPump" begin
    # The ideal pump is a transformer: Q = D*w, T = D*dp, P_mech = dp*Q.
    @testset "ideal pump" begin
        D = 2.0e-6
        w, p_a, p_b = 150.0, 1.0e5, 2.0e7
        dp = p_b - p_a
        columns, result, flat = bg_run(_fdp_model(w, p_a, p_b,
            Dict("D" => string(D), "eta_v" => "1.0", "eta_m" => "1.0")))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        Q = bg_value(columns, "P1/Q", 0.01)
        T = bg_value(columns, "P1/T", 0.01)
        @test isapprox(Q, D * w; rtol = 1e-12)
        @test isapprox(T, D * dp; rtol = 1e-12)
        @test isapprox(T * w, dp * Q; rtol = 1e-12)
        @test isapprox(bg_value(columns, "P1/shaft.P", 0.01), dp * Q; rtol = 1e-12)
        @test abs(bg_value(columns, "P1/P_loss", 0.01)) <= 1e-9 * dp * Q
        @test isapprox(bg_value(columns, "P1/a.f", 0.01), Q; rtol = 1e-12)
        @test isapprox(bg_value(columns, "P1/b.f", 0.01), -Q; rtol = 1e-12)
    end

    # The lossy pump at the nominal point meets eta_v and eta_m (to the tanh roundings).
    @testset "efficiencies at the nominal point" begin
        p_a, p_b = 1.0e5, 1.01e7
        dp = p_b - p_a
        columns, result, _ = bg_run(_fdp_model(157.0, p_a, p_b, Dict{String,Any}()))
        @test result.status == "done"
        Q = bg_value(columns, "P1/Q", 0.01)
        T = bg_value(columns, "P1/T", 0.01)
        @test isapprox(Q / (1.6e-6 * 157.0), 0.95; rtol = 1e-9)
        @test isapprox(1.6e-6 * dp / T, 0.9; rtol = 1e-9)
        # Overall efficiency = hydraulic power out / mechanical power in = eta_v*eta_m.
        @test isapprox(dp * Q / (T * 157.0), 0.95 * 0.9; rtol = 1e-9)
    end

    # All four quadrants: the law, P_loss >= 0, and the port power balance.
    @testset "w = $w, p_a = $p_a, p_b = $p_b" for (w, p_a, p_b) in (
        (100.0, 1.0e5, 1.5e7),     # pumping
        (-100.0, 1.0e5, 1.5e7),    # reversed rotation against the pressure (motoring)
        (100.0, 1.5e7, 1.0e5),     # pressure aiding the rotation
        (0.3, 1.0e5, 3.0e6),       # inside the friction speed band
        (50.0, 1.0e5, 1.2e5),      # inside the pressure band
        (0.0, 1.0e5, 1.0e5),       # standstill, no pressure: everything zero
    )
        dp = p_b - p_a
        Q, T, P_loss = _fdp_law(w, dp)
        columns, result, _ = bg_run(_fdp_model(w, p_a, p_b, Dict{String,Any}()))
        @test result.status == "done"
        for t in (0.0, 0.01)
            @test isapprox(bg_value(columns, "P1/dp", t), dp; rtol = 1e-12, atol = 1e-9)
            @test isapprox(bg_value(columns, "P1/Q", t), Q; rtol = 1e-9, atol = 1e-18)
            @test isapprox(bg_value(columns, "P1/T", t), T; rtol = 1e-9, atol = 1e-12)
            @test isapprox(bg_value(columns, "P1/P_loss", t), P_loss; rtol = 1e-9, atol = 1e-12)
            @test bg_value(columns, "P1/P_loss", t) >= -1e-12
            # The power into the block through its three ports is what it dissipates.
            P_in = bg_value(columns, "P1/shaft.P", t) + bg_value(columns, "P1/a.P", t) +
                   bg_value(columns, "P1/b.P", t)
            @test isapprox(P_in, P_loss; rtol = 1e-7, atol = 1e-9)
        end
    end
end
