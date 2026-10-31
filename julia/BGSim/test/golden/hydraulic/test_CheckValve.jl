# Golden test for `stdlib:hydraulic/CheckValve`, through the real pipeline.
#
# Model: a `PressureSource` holds a at p_a, a `Tank` holds b at p_b. With dp = p_a - p_b:
#
#   x = (sqrt(s^2 + 1e-6) - sqrt((s - 1)^2 + 1e-6) + 1)/2,  s = (dp - p_crack)/dp_open,
#   A = A_leak + (A_max - A_leak)*x,
#   Q = Cd*A*dp*sqrt(2/(rho*sqrt(dp^2 + p_tr^2)))
#     = Cd*A*sqrt(2/rho)*dp/(dp^2 + p_tr^2)^(1/4)   (the Orifice's regularized law).
#
# Checks: the law at every operating region (rtol 1e-9); below cracking the valve is
# essentially closed, above p_crack + dp_open it is fully open, and a reverse pressure
# passes only the leakage (at the same |dp| the reverse flow is below 1e-5 of the forward
# flow); the valve only dissipates, dp*Q >= 0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _cv_law(dp; p_crack = 1.0e5, dp_open = 2.0e5, A_max = 1.0e-5, A_leak = 1.0e-11,
    Cd = 0.62, rho = 850.0, p_tr = 1.0e5)
    s = (dp - p_crack) / dp_open
    x = 0.5 * (sqrt(s^2 + 1e-6) - sqrt((s - 1)^2 + 1e-6) + 1)
    A = A_leak + (A_max - A_leak) * x
    return Cd * A * sqrt(2 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4), x
end

function _cv_model(p_a, p_b)
    return bg_model(
        "CheckValveBetweenSourceAndTank",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "PS", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(p_a))),
            bg_node("n3", "CV", bg_ref("stdlib:hydraulic/CheckValve")),
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
end

@testset "golden: CheckValve" begin
    flows = Dict{Float64,Float64}()
    @testset "dp = $dp" for dp in (5.0e6, 2.0e5, 1.0e5, 5.0e4, 0.0, -5.0e4, -5.0e6)
        p_b = 1.0e5
        Q, x = _cv_law(dp)
        columns, result, flat = bg_run(_cv_model(p_b + dp, p_b))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        for t in (0.0, 0.01)
            @test isapprox(bg_value(columns, "CV/dp", t), dp; atol = 1e-6)
            @test isapprox(bg_value(columns, "CV/x", t), x; rtol = 1e-9, atol = 1e-15)
            @test isapprox(bg_value(columns, "CV/Q", t), Q; rtol = 1e-9, atol = 1e-20)
            @test isapprox(bg_value(columns, "CV/a.f", t), Q; rtol = 1e-9, atol = 1e-20)
            @test isapprox(bg_value(columns, "CV/b.f", t), -Q; rtol = 1e-9, atol = 1e-20)
            # Passive: the power into the valve dp*Q is never negative.
            P = bg_value(columns, "CV/a.P", t) + bg_value(columns, "CV/b.P", t)
            @test P >= -1e-12
            @test isapprox(P, dp * Q; rtol = 1e-9, atol = 1e-15)
        end
        flows[dp] = bg_value(columns, "CV/Q", 0.01)
    end
    # Fully open well above p_crack + dp_open, closed well below p_crack.
    @test _cv_law(5.0e6)[2] > 0.9999
    @test _cv_law(-5.0e6)[2] < 1e-9
    # Reverse flow is blocked: only the leakage passes.
    @test flows[-5.0e6] < 0
    @test abs(flows[-5.0e6]) < 1e-5 * flows[5.0e6]
    @test flows[0.0] == 0.0
    # Monotone in dp.
    dps = sort(collect(keys(flows)))
    @test issorted([flows[d] for d in dps])
end
