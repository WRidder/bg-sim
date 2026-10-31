# Golden test for `stdlib:converters/VariableDisplacementPump`, through the real pipeline.
#
# Model: a `SpeedSource` turns the shaft at w, a `Constant` sets the displacement fraction
# u, and two `Tank`s hold the suction a and the delivery b. With dp = p_b - p_a:
#
#   Q = D*u*w - K_leak*dp,                          K_leak = D*w_nom*(1 - eta_v)/p_nom,
#   T = D*u*dp + K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr),  K_fr = D*(1 - eta_m)/eta_m.
#
# Checks: the law at full, part, zero and negative (over-centre) displacement; the ideal
# pump scales its delivery with u and stays lossless; the losses are never negative and the
# port powers balance.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _vdp_law(w, dp, u; D = 1.6e-6, eta_v = 0.95, eta_m = 0.9, p_nom = 1.0e7,
    w_nom = 157.0, p_tr = 1.0e5, w_tr = 1.0)
    K_leak = D * w_nom * (1 - eta_v) / p_nom
    K_fr = D * (1 - eta_m) / eta_m
    Q = D * u * w - K_leak * dp
    T = D * u * dp + K_fr * dp * tanh(dp / p_tr) * tanh(w / w_tr)
    return Q, T, K_leak * dp^2 + K_fr * dp * tanh(dp / p_tr) * tanh(w / w_tr) * w
end

function _vdp_model(w, u, p_a, p_b, params)
    return bg_model(
        "VariablePumpBetweenTanks",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "P1", bg_ref("stdlib:converters/VariableDisplacementPump");
                params = Dict{String,Any}(params)),
            bg_node("n4", "TA", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_a))),
            bg_node("n5", "TB", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_b))),
            bg_node("n6", "U1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(u))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "shaft"),
            bg_conn("c3", "wire", "n4", "a", "n3", "a"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
            bg_conn("c5", "signal", "n6", "y", "n3", "u"),
        ];
        t_end = 0.01, points = 3,
    )
end

@testset "golden: VariableDisplacementPump" begin
    @testset "ideal pump, u = $u" for u in (1.0, 0.4, 0.0, -0.6)
        D, w, p_a, p_b = 2.0e-6, 120.0, 1.0e5, 1.0e7
        dp = p_b - p_a
        columns, result, flat = bg_run(_vdp_model(w, u, p_a, p_b,
            Dict("D" => string(D), "eta_v" => "1.0", "eta_m" => "1.0")))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        Q = bg_value(columns, "P1/Q", 0.01)
        T = bg_value(columns, "P1/T", 0.01)
        @test isapprox(Q, D * u * w; rtol = 1e-12, atol = 1e-20)
        @test isapprox(T, D * u * dp; rtol = 1e-12, atol = 1e-12)
        @test isapprox(T * w, dp * Q; rtol = 1e-12, atol = 1e-12)
        @test abs(bg_value(columns, "P1/P_loss", 0.01)) <= 1e-12
    end

    @testset "lossy pump, w = $w, u = $u, dp = $(p_b - p_a)" for (w, u, p_a, p_b) in (
        (157.0, 1.0, 1.0e5, 1.01e7),   # the nominal point at full stroke
        (157.0, 0.5, 1.0e5, 1.01e7),   # half stroke: same leakage, half the delivery
        (157.0, 0.0, 1.0e5, 1.01e7),   # zero stroke: only the leakage flows back
        (157.0, -0.5, 1.0e7, 1.0e5),   # over-centre: delivers from b to a
        (-80.0, 0.8, 1.0e5, 5.0e6),    # back-driven
    )
        dp = p_b - p_a
        Q, T, P_loss = _vdp_law(w, dp, u)
        columns, result, _ = bg_run(_vdp_model(w, u, p_a, p_b, Dict{String,Any}()))
        @test result.status == "done"
        @test isapprox(bg_value(columns, "P1/Q", 0.01), Q; rtol = 1e-9, atol = 1e-18)
        @test isapprox(bg_value(columns, "P1/T", 0.01), T; rtol = 1e-9, atol = 1e-12)
        @test isapprox(bg_value(columns, "P1/P_loss", 0.01), P_loss; rtol = 1e-9)
        @test P_loss >= 0
        P_in = bg_value(columns, "P1/shaft.P", 0.01) + bg_value(columns, "P1/a.P", 0.01) +
               bg_value(columns, "P1/b.P", 0.01)
        @test isapprox(P_in, P_loss; rtol = 1e-7, atol = 1e-9)
    end
    # At full stroke and the nominal point the volumetric efficiency is eta_v.
    let (Q, _, _) = _vdp_law(157.0, 1.0e7, 1.0)
        @test isapprox(Q / (1.6e-6 * 157.0), 0.95; rtol = 1e-12)
    end
end
