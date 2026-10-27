# Golden test for `stdlib:hydraulic/Tank` (plan section 8, M2 row: Tank), through the real
# pipeline.
#
# Hydraulic convention (D8): across = `e` (pressure). A tank holds its port at `p` and has
# no flow equation of its own, so it absorbs whatever flow the rest of the circuit sends it.
# Model: a `PressureSource` at 100 bar drives an `Orifice` into the tank at 1 bar; the tank
# must sit at exactly 1 bar and receive the whole orifice flow.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function tank_orifice_flow(dp; Cd = 0.62, A = 1.0e-6, rho = 850.0, p_tr = 1.0e5)
    return Cd * A * sqrt(2.0 / rho) * dp / (dp^2 + p_tr^2)^(1 / 4)
end

@testset "golden: Tank" begin
    p_hi = 1.0e7
    p_lo = 1.0e5
    dp = p_hi - p_lo
    Q = tank_orifice_flow(dp)

    model = bg_model(
        "TankAbsorbsOrificeFlow",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "P1", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(p_hi))),
            bg_node("n3", "O1", bg_ref("stdlib:hydraulic/Orifice")),
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
        @test isapprox(bg_value(columns, "T1/a.e", t), p_lo; rtol = 1e-9)
        @test isapprox(bg_value(columns, "O1/b.e", t), p_lo; rtol = 1e-9)
        # The tank receives the orifice flow and dissipates no power (its flow is a wire
        # balance, not a loss): P = p_lo * Q with the sign of the incoming bond.
        @test isapprox(bg_value(columns, "T1/a.f", t), Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "T1/a.P", t), p_lo * Q; rtol = 1e-9)
    end
end
