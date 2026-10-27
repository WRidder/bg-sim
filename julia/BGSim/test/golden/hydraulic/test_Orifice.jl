# Golden test for `stdlib:hydraulic/Orifice` (plan section 8, M2 row: Orifice), through the
# real pipeline.
#
# Model: a `PressureSource` at p_hi drives the orifice into a `Tank` at p_low. With
# dp = p_hi - p_low the plan's regularized law is
#
#   Q = Cd*A*sqrt(2/rho) * dp/(dp^2 + p_tr^2)^(1/4).
#
# The test covers the two limits the regularization is for: high dp (the p_tr term is
# negligible) and low dp (the p_tr term dominates and the flow stays linear), plus exactly
# dp = 0 and the reversed direction. Tolerance: rtol 1e-9 against the analytic law.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function orifice_law(dp; Cd = 0.62, A = 1.0e-6, rho = 850.0, p_tr = 1.0e5)
    return Cd * A * sqrt(2.0 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4)
end

function orifice_model(p_hi, p_low)
    return bg_model(
        "OrificeBetweenPressureSourceAndTank",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "P1", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(p_hi))),
            bg_node("n3", "O1", bg_ref("stdlib:hydraulic/Orifice")),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_low))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: Orifice" begin
    for (p_hi, p_low) in (
        (1.0e7, 1.0e5),          # high dp: 99 bar, p_tr negligible
        (1.005e5, 1.0e5),        # low dp: 500 Pa, p_tr dominates (linear regime)
        (1.0e5, 1.0e5),          # dp = 0 exactly: Q = 0, no division by zero
        (1.0e5, 1.0e7),          # reversed: Q < 0
    )
        dp = p_hi - p_low
        Q = orifice_law(dp)
        columns, result, flat = bg_run(orifice_model(p_hi, p_low))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        for t in (0.0, 0.005, 0.01)
            @test isapprox(bg_value(columns, "O1/dp", t), dp; rtol = 1e-12, atol = 1e-9)
            @test isapprox(bg_value(columns, "O1/Q", t), Q; rtol = 1e-9, atol = 1e-18)
            @test isapprox(bg_value(columns, "O1/a.f", t), Q; rtol = 1e-9, atol = 1e-18)
            @test isapprox(bg_value(columns, "O1/b.f", t), -Q; rtol = 1e-9, atol = 1e-18)
            # Power in equals dp*Q; it is dissipated, never generated.
            @test isapprox(bg_value(columns, "O1/a.P", t) + bg_value(columns, "O1/b.P", t),
                dp * Q; rtol = 1e-9, atol = 1e-18)
        end
    end

    # The high-dp limit is close to the unregularized law, and the low-dp limit is the
    # linear asymptote. Both are checked to 1e-3/1e-5: the low-dp form differs from the
    # exact law by the O((dp/p_tr)^2) = 2.5e-5 term of the fourth root, which is 6.25e-6
    # in Q.
    dp_hi = 9.9e6
    @test isapprox(orifice_law(dp_hi),
        0.62 * 1.0e-6 * sqrt(2.0 / 850.0) * sqrt(dp_hi); rtol = 1e-3)
    dp_lo = 500.0
    @test isapprox(orifice_law(dp_lo),
        0.62 * 1.0e-6 * sqrt(2.0 / 850.0) * dp_lo / sqrt(1.0e5); rtol = 1e-5)
end
