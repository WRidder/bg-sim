# Golden test for `stdlib:hydraulic/VariableOrifice` (plan section 8, M2 row: Variable
# orifice), through the real pipeline.
#
# Model: a `PressureSource` at 100 bar drives the valve into a `Tank` at 1 bar; a `Constant`
# sets the area command `u`. The area is `A*u`, so the regularized law
#
#   Q = Cd*(A*u)*sqrt(2/rho) * dp/(dp^2 + p_tr^2)^(1/4)
#
# scales linearly with u, and u = 0 closes the valve exactly. Tolerance: rtol 1e-9.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function variable_orifice_law(dp, u; Cd = 0.62, A = 1.0e-6, rho = 850.0, p_tr = 1.0e5)
    return Cd * A * u * sqrt(2.0 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4)
end

function variable_orifice_model(u)
    return bg_model(
        "VariableOrificeCommanded",
        [
            bg_node("n0", "C0", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(u))),
            bg_node("n2", "P1", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => "1.0e7")),
            bg_node("n3", "V1", bg_ref("stdlib:hydraulic/VariableOrifice")),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank")),
        ],
        [
            bg_conn("c0", "signal", "n0", "y", "n2", "u"),
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.01, points = 11,
    )
end

@testset "golden: VariableOrifice" begin
    dp = 1.0e7 - 1.0e5
    for u in (1.0, 0.5, 0.25, 0.0)
        Q = variable_orifice_law(dp, u)
        columns, result, flat = bg_run(variable_orifice_model(u))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 0
        for t in (0.0, 0.005, 0.01)
            @test isapprox(bg_value(columns, "V1/u", t), u; rtol = 1e-12, atol = 1e-15)
            @test isapprox(bg_value(columns, "V1/dp", t), dp; rtol = 1e-12, atol = 1e-9)
            @test isapprox(bg_value(columns, "V1/Q", t), Q; rtol = 1e-9, atol = 1e-18)
            @test isapprox(bg_value(columns, "V1/a.f", t), Q; rtol = 1e-9, atol = 1e-18)
            @test isapprox(bg_value(columns, "V1/b.f", t), -Q; rtol = 1e-9, atol = 1e-18)
        end
        # The command scales the flow linearly (the area is linear in u).
        @test isapprox(Q, u * variable_orifice_law(dp, 1.0); rtol = 1e-12, atol = 1e-18)
    end
end
