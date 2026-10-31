# Golden test for `stdlib:hydraulic/PressureCompensatedFlowControl`, through the real
# pipeline.
#
# Model: a `PressureSource` holds a at p_b + dp, a `Tank` holds b, and a `Constant` sets
# the throttle command u. With the compensator setting dp_c = 10 bar:
#
#   m = dp/(1 + (dp/dp_c)^8)^(1/8),   Q = Q_nom*u*g(m)/g(dp_c),  g(x) = x/(x^2 + p_tr^2)^(1/4).
#
# Checks: the law at rtol 1e-9; above about 2*dp_c the flow is regulated to Q_nom*u within
# 1e-3 whatever the pressure drop (30 to 200 bar); below dp_c it falls off like an orifice
# (about sqrt(dp/dp_c)); no flow without a pressure drop; the valve only dissipates.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _pcfc_law(dp, u; Q_nom = 1.0e-4, dp_c = 1.0e6, p_tr = 1.0e5)
    g(x) = x / (x^2 + p_tr^2)^(1 / 4)
    m = dp / (1 + (dp / dp_c)^8)^(1 / 8)
    return Q_nom * u * g(m) / g(dp_c)
end

@testset "golden: PressureCompensatedFlowControl" begin
    flows = Dict{Tuple{Float64,Float64},Float64}()
    @testset "dp = $dp, u = $u" for (dp, u) in (
        (2.0e7, 1.0), (1.0e7, 1.0), (3.0e6, 1.0), (2.0e7, 0.5), (3.0e6, 0.5),
        (1.0e6, 1.0), (2.5e5, 1.0), (0.0, 1.0), (-3.0e6, 1.0),
    )
        p_b = 1.0e5
        Q = _pcfc_law(dp, u)
        model = bg_model(
            "FlowControlBetweenSourceAndTank",
            [
                bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0")),
                bg_node("n2", "PS", bg_ref("stdlib:hydraulic/PressureSource");
                    params = Dict{String,Any}("p" => string(p_b + dp))),
                bg_node("n3", "FC", bg_ref("stdlib:hydraulic/PressureCompensatedFlowControl")),
                bg_node("n4", "TK", bg_ref("stdlib:hydraulic/Tank");
                    params = Dict{String,Any}("p" => string(p_b))),
                bg_node("n5", "U1", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => string(u))),
            ],
            [
                bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "wire", "n2", "a", "n3", "a"),
                bg_conn("c3", "wire", "n3", "b", "n4", "a"),
                bg_conn("c4", "signal", "n5", "y", "n3", "u"),
            ];
            t_end = 0.01, points = 3,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test flat.stats.states == 0
        @test isapprox(bg_value(columns, "FC/Q", 0.01), Q; rtol = 1e-9, atol = 1e-20)
        @test isapprox(bg_value(columns, "FC/a.f", 0.01), Q; rtol = 1e-9, atol = 1e-20)
        @test dp * bg_value(columns, "FC/Q", 0.01) >= 0
        flows[(dp, u)] = bg_value(columns, "FC/Q", 0.01)
    end
    # Regulated flow: independent of the load pressure above about 2*dp_c.
    for dp in (3.0e6, 1.0e7, 2.0e7)
        @test isapprox(flows[(dp, 1.0)], 1.0e-4; rtol = 1e-3)
    end
    @test isapprox(flows[(2.0e7, 0.5)], 0.5e-4; rtol = 1e-3)
    @test isapprox(flows[(3.0e6, 0.5)], 0.5e-4; rtol = 1e-3)
    # Below dp_c the throttle sees the whole drop: about sqrt(dp/dp_c) of the setting.
    @test isapprox(flows[(2.5e5, 1.0)], 1.0e-4 * sqrt(0.25); rtol = 0.05)
    @test flows[(0.0, 1.0)] == 0.0
    @test flows[(-3.0e6, 1.0)] < 0
end
