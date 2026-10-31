# Golden test for `stdlib:hydraulic/PressureReliefValve`, through the real pipeline.
#
# 1. Static: a `PressureSource` holds a at p_a, a `Tank` holds b at 1 bar; the flow follows
#    the Orifice's regularized law with the opening x of the smooth clamp of
#    (dp - p_set)/dp_reg (rtol 1e-9).
# 2. Pressure capping: a `FlowSource` pushes Q_in = 1e-4 m^3/s into a `Volume`
#    (V = 1e-4 m^3, beta = 1.4e9 Pa) protected by the relief valve to a 1 bar tank. Until
#    the valve cracks the pressure rises linearly, p = beta*Q_in*t/V (the leakage is
#    ~1e-5 of Q_in); then it settles where the valve passes Q_in. The steady pressure is
#    solved from the valve law by bisection and must lie inside [p_set, p_set + dp_reg],
#    and the pressure never overshoots p_set + dp_reg.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _prv_law(dp; p_set = 1.0e7, dp_reg = 5.0e5, A_max = 5.0e-5, A_leak = 1.0e-11,
    Cd = 0.62, rho = 850.0, p_tr = 1.0e5)
    s = (dp - p_set) / dp_reg
    x = 0.5 * (sqrt(s^2 + 1e-6) - sqrt((s - 1)^2 + 1e-6) + 1)
    A = A_leak + (A_max - A_leak) * x
    return Cd * A * sqrt(2 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4), x
end

@testset "golden: PressureReliefValve" begin
    @testset "static, dp = $dp" for dp in (2.0e7, 1.03e7, 1.0e7, 5.0e6, 0.0, -1.0e6)
        p_b = 1.0e5
        Q, x = _prv_law(dp)
        model = bg_model(
            "ReliefValveBetweenSourceAndTank",
            [
                bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0")),
                bg_node("n2", "PS", bg_ref("stdlib:hydraulic/PressureSource");
                    params = Dict{String,Any}("p" => string(p_b + dp))),
                bg_node("n3", "RV", bg_ref("stdlib:hydraulic/PressureReliefValve")),
                bg_node("n4", "TK", bg_ref("stdlib:hydraulic/Tank");
                    params = Dict{String,Any}("p" => string(p_b))),
            ],
            [
                bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "wire", "n2", "a", "n3", "a"),
                bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            ];
            t_end = 0.01, points = 3,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test flat.stats.states == 0
        @test isapprox(bg_value(columns, "RV/x", 0.01), x; rtol = 1e-9, atol = 1e-15)
        @test isapprox(bg_value(columns, "RV/Q", 0.01), Q; rtol = 1e-9, atol = 1e-20)
        @test dp * bg_value(columns, "RV/Q", 0.01) >= 0
    end
    @test _prv_law(2.0e7)[2] > 0.9999      # fully open
    @test _prv_law(5.0e6)[2] < 1e-8        # closed

    @testset "caps the pressure of a flow-fed volume" begin
        Q_in, V, beta, p_t = 1.0e-4, 1.0e-4, 1.4e9, 1.0e5
        model = bg_model(
            "ReliefValveCapsVolume",
            [
                bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0")),
                bg_node("n2", "F1", bg_ref("stdlib:hydraulic/FlowSource");
                    params = Dict{String,Any}("Q" => string(-Q_in))),
                bg_node("n3", "V1", bg_ref("stdlib:hydraulic/Volume");
                    params = Dict{String,Any}("V" => string(V), "beta" => string(beta))),
                bg_node("n4", "RV", bg_ref("stdlib:hydraulic/PressureReliefValve")),
                bg_node("n5", "TK", bg_ref("stdlib:hydraulic/Tank");
                    params = Dict{String,Any}("p" => string(p_t))),
            ],
            [
                bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "wire", "n2", "a", "n3", "a"),
                bg_conn("c3", "wire", "n3", "a", "n4", "a"),
                bg_conn("c5", "wire", "n4", "b", "n5", "a"),
                bg_conn("c6", "wire", "n2", "b", "n5", "a"),
            ];
            t_end = 0.05, points = 501,
        )
        columns, result, _ = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test !any(d -> d.code == "W206", result.diagnostics)
        # Before cracking (p < 9 MPa until t = 6.4 ms): the linear charge of the volume.
        for t in (1.0e-3, 3.0e-3, 6.0e-3)
            @test isapprox(bg_value(columns, "V1/p", t), beta * Q_in * t / V; rtol = 1e-4)
        end
        # The steady pressure: the valve passes Q_in.
        lo, hi = 1.0e7 - 1.0e5, 1.05e7 + 1.0e5
        for _ in 1:200
            mid = (lo + hi) / 2
            _prv_law(mid - p_t)[1] < Q_in ? (lo = mid) : (hi = mid)
        end
        p_ss = (lo + hi) / 2
        @test 1.0e7 <= p_ss - p_t <= 1.0e7 + 5.0e5
        @test isapprox(bg_value(columns, "V1/p", 0.05), p_ss; rtol = 1e-7)
        @test isapprox(bg_value(columns, "RV/Q", 0.05), Q_in; rtol = 1e-6)
        # Never above the fully open pressure.
        @test maximum(columns["V1/p"]) <= p_t + 1.0e7 + 5.0e5
    end
end
