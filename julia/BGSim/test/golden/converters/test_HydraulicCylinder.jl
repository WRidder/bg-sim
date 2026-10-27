# Golden test for `stdlib:converters/HydraulicCylinder` (plan section 8, M2 row: Hydraulic
# cylinder), through the real pipeline.
#
# Model: a `FlowSource` (Q = -1e-6 m^3/s, so +1e-6 enters chamber A) feeds `A`; its return
# port goes to a 1 bar tank. Chamber `B` is held at 0 Pa by a tank, and the rod is held at
# zero speed by a `VelocitySource` (v = 0). With Ap = 2e-3 m^2, Ar = 1e-3 m^2,
# V0A = 5e-5 m^3 and beta = 1.4e9 Pa:
#
#   x = 0,  rod.f = 0,  pA(t) = beta*Q_A*t/V0A = 2.8e7*t Pa,  pB = 0,
#   rod.e = pB*Ar - pA*Ap = -56000*t N,  A.f = 1e-6,  B.f = 0.
#
# The hydraulic charging work pA*Q_A equals the stored compressibility energy
# V0A/(2*beta)*pA^2.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: HydraulicCylinder" begin
    Q = -1.0e-6
    Q_A = -Q
    Ap = 2.0e-3
    Ar = 1.0e-3
    V0A = 5.0e-5
    beta = 1.4e9
    rate = beta * Q_A / V0A

    model = bg_model(
        "HydraulicCylinderChamberCompressibility",
        [
            bg_node("n0", "C0", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n1", "F1", bg_ref("stdlib:hydraulic/FlowSource");
                params = Dict{String,Any}("Q" => string(Q))),
            bg_node("n2", "C1", bg_ref("stdlib:converters/HydraulicCylinder");
                params = Dict{String,Any}(
                    "Ap" => string(Ap), "Ar" => string(Ar), "V0A" => string(V0A),
                    "V0B" => "5.0e-5", "beta" => string(beta), "stroke" => "0.2")),
            bg_node("n3", "T1", bg_ref("stdlib:hydraulic/Tank")),
            bg_node("n4", "T2", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => "0.0")),
            bg_node("n5", "C5", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n6", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "0.0")),
        ],
        [
            bg_conn("c1", "signal", "n0", "y", "n1", "u"),
            bg_conn("c2", "wire", "n1", "a", "n2", "A"),
            bg_conn("c3", "wire", "n1", "b", "n3", "a"),
            bg_conn("c4", "wire", "n4", "a", "n2", "B"),
            bg_conn("c5", "signal", "n5", "y", "n6", "u"),
            bg_conn("c6", "wire", "n2", "rod", "n6", "a"),
        ];
        t_end = 1.0e-3, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 3                 # x, pA, pB
    for t in (0.0, 2.0e-4, 5.0e-4, 1.0e-3)
        pA = rate * t
        @test isapprox(bg_value(columns, "C1/x", t), 0.0; atol = 1e-15)
        @test isapprox(bg_value(columns, "C1/rod.f", t), 0.0; atol = 1e-15)
        @test isapprox(bg_value(columns, "C1/A.f", t), Q_A; rtol = 1e-9)
        @test isapprox(bg_value(columns, "C1/B.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "C1/pA", t), pA; rtol = 1e-9, atol = 1e-9)
        @test isapprox(bg_value(columns, "C1/pB", t), 0.0; atol = 1e-9)
        @test isapprox(bg_value(columns, "C1/rod.e", t), -pA * Ap; rtol = 1e-9,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), pA * Ap; rtol = 1e-9, atol = 1e-9)
        # Charging work equals the stored energy in chamber A.
        work = Q_A * 0.5 * rate * t^2
        stored = V0A / (2.0 * beta) * pA^2
        @test isapprox(work, stored; rtol = 1e-9)
    end
end
