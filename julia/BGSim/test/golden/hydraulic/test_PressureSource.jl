# Golden test for `stdlib:hydraulic/PressureSource` (plan section 8, M2 row: Pressure
# source), through the real pipeline.
#
# Hydraulic convention (D8): across = `e` (pressure), through = `f` (volume flow). A wire
# equates the pressures and sums the flows to zero. Model: the source holds a node at
# `p*u`; a regularized `Orifice` and a `Tank` at 1 bar complete the circuit, so the source
# also has to supply the orifice flow. With dp = p_hi - p_tank,
#
#   Q = Cd*A*sqrt(2/rho) * dp/(dp^2 + p_tr^2)^(1/4).
#
# Tolerance: rtol 1e-9 for the algebraic pressures and flows (reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function pressure_orifice_flow(dp; Cd = 0.62, A = 1.0e-6, rho = 850.0, p_tr = 1.0e5)
    return Cd * A * sqrt(2.0 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4)
end

@testset "golden: PressureSource" begin
    p_hi = 1.0e7          # 100 bar
    p_lo = 1.0e5          # 1 bar
    Cd = 0.62
    A = 1.0e-6
    rho = 850.0
    p_tr = 1.0e5
    dp = p_hi - p_lo
    Q = pressure_orifice_flow(dp; Cd = Cd, A = A, rho = rho, p_tr = p_tr)

    model = bg_model(
        "PressureSourceDrivesOrifice",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "P1", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(p_hi))),
            bg_node("n3", "O1", bg_ref("stdlib:hydraulic/Orifice");
                params = Dict{String,Any}(
                    "Cd" => string(Cd), "A" => string(A), "rho" => string(rho),
                    "p_tr" => string(p_tr))),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_lo))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "P1/u", t), 1.0; rtol = 1e-12)
        @test isapprox(bg_value(columns, "P1/a.e", t), p_hi; rtol = 1e-9)
        @test isapprox(bg_value(columns, "O1/a.e", t), p_hi; rtol = 1e-9)
        @test isapprox(bg_value(columns, "O1/b.e", t), p_lo; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T1/a.e", t), p_lo; rtol = 1e-9)
        # The orifice draws Q from the source node, so the source flow is -Q.
        @test isapprox(bg_value(columns, "O1/a.f", t), Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "O1/b.f", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "P1/a.f", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T1/a.f", t), Q; rtol = 1e-9)
        # Power: the source delivers exactly what the orifice dissipates.
        @test isapprox(bg_value(columns, "P1/a.P", t), -p_hi * Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "O1/a.P", t) + bg_value(columns, "O1/b.P", t),
            dp * Q; rtol = 1e-9)
        @test abs(bg_value(columns, "P1/a.P", t) + bg_value(columns, "O1/a.P", t) +
                  bg_value(columns, "O1/b.P", t) + bg_value(columns, "T1/a.P", t)) <= 1e-9
    end
end
