# Golden test for `stdlib:continuous/PID` (plan section 8, M2 row: PID), through the real
# pipeline. The block has a filtered derivative and back-calculation anti-windup:
#   v = Kp*e + (Kp/Ti)*xi + N*(e - xd),   xi' = e/Ti + (y - v)/Tt,  xd' = (e - xd)*N/Td,
#   y = clamp(v, lower, upper),           Tt = sqrt(Ti*Td).
#
# Model: a Constant error e = 1 drives two PIDs.
#   A: limits at +-1e30 (never saturated, so y = v). With xd(0) = 0, xi(0) = 0 and e = 1:
#        v(t) = Kp + (Kp/Ti^2)*t + N*exp(-N*t/Td).
#   B: upper = 0.8. The output saturates and the back-calculation term balances the
#      integral: at equilibrium y = upper, v = upper + Tt/Ti, xi = (v - Kp)/(Kp/Ti).
#
# Reference: the analytic A response and the analytic B equilibrium.
# Tolerance: rtol 1e-6 at the sampled points (reltol 1e-10 in the run).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: PID" begin
    Kp, Ti, Td, N = 1.0, 0.5, 0.01, 10.0
    Tt = sqrt(Ti * Td)
    upper = 0.8

    model = bg_model(
        "PidAgainstAnalyticResponse",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "A", bg_ref("stdlib:continuous/PID");
                params = Dict{String,Any}("Kp" => string(Kp), "Ti" => string(Ti),
                    "Td" => string(Td), "N" => string(N),
                    "lower" => "-1.0e30", "upper" => "1.0e30")),
            bg_node("n3", "B", bg_ref("stdlib:continuous/PID");
                params = Dict{String,Any}("Kp" => string(Kp), "Ti" => string(Ti),
                    "Td" => string(Td), "N" => string(N),
                    "lower" => "-1.0e30", "upper" => string(upper))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n1", "y", "n3", "u"),
        ];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 4               # xi and xd of each of the two PIDs

    # A is not saturated: y = v with xd(t) = 1 - exp(-N*t/Td), xi(t) = u*t/Ti and u = 1.
    free(t) = Kp + (Kp / Ti^2) * t + N * exp(-N * t / Td)
    for t in (0.0, 0.05, 0.2, 0.5, 1.0, 2.0)
        @test isapprox(bg_value(columns, "A/y", t), free(t); rtol = 1e-6, atol = 1e-6)
    end

    # B saturates at the upper limit, and back-calculation holds the integral at the
    # equilibrium that makes v - y = Tt*e/Ti without winding up.
    v_eq = upper + Tt / Ti
    xi_eq = (v_eq - Kp) / (Kp / Ti)
    @test isapprox(bg_value(columns, "B/y", 2.0), upper; rtol = 1e-9)
    @test isapprox(bg_value(columns, "B/v", 2.0), v_eq; rtol = 1e-6)
    @test isapprox(bg_value(columns, "B/xi", 2.0), xi_eq; rtol = 1e-6, atol = 1e-9)
    @test all(bg_all(columns, "B/y") .<= upper + 1e-9)
end
