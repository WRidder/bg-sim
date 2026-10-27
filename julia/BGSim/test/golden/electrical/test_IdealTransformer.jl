# Golden test for `stdlib:electrical/IdealTransformer` (plan section 8, M2 row: Ideal
# transformer), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a 10 V source feeds the primary winding (p1 at the source node, n1 at ground). The
# secondary (p2 at its node, n2 at ground) feeds a 1 kOhm resistor in series with a 1 uF
# capacitor to ground, so the capacitor voltage is a real state (no raised DAE index). The
# turns ratio is n = 2.
#
# Reference: the lossless transformer fixes v2 = v1/n = 5 V, and the secondary is then a plain
# RC charge:
#   v_C(t) = (V/n)*(1 - exp(-t/(R*C))),
#   i_R = (V/n - v_C)/R,  p2.f = -i_R,  p1.f = -p2.f/n = i_R/n.
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10), plus
# the turns ratio, the power balance of both windings and the source power.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: IdealTransformer" begin
    V = 10.0
    n = 2.0
    R = 1.0e3
    C = 1.0e-6
    tau = R * C
    v2 = V / n
    capacitor_voltage(t) = v2 * (1.0 - exp(-t / tau))
    resistor_current(t) = (v2 - capacitor_voltage(t)) / R

    model = bg_model(
        "IdealTransformerDrivesRC",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "10.0")),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => "1.0")),
            bg_node("n3", "T1", bg_ref("stdlib:electrical/IdealTransformer");
                params = Dict{String,Any}("n" => "2.0")),
            bg_node("n4", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "1.0e3")),
            bg_node("n5", "K1", bg_ref("stdlib:electrical/Capacitor");
                params = Dict{String,Any}("C" => "1.0e-6")),
            bg_node("n6", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p1"),
            bg_conn("c3", "wire", "n2", "n", "n3", "n1"),
            bg_conn("c4", "wire", "n3", "p2", "n4", "p"),
            bg_conn("c5", "wire", "n4", "n", "n5", "p"),
            bg_conn("c6", "wire", "n2", "n", "n6", "p"),
            bg_conn("c7", "wire", "n3", "n2", "n6", "p"),
            bg_conn("c8", "wire", "n5", "n", "n6", "p"),
        ];
        t_end = 0.005, points = 51,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    # The series resistor keeps the capacitor a differential state (plan: no raised index).
    @test flat.stats.states == 1
    @test isempty([d for d in result.diagnostics if d.code == "W201"])

    for t in (0.0, 1.0e-4, 5.0e-4, 1.0e-3, 5.0e-3)
        # The windings: v1 = n*v2 and p1.f = -p2.f/n (power conserving, power positive into
        # each winding).
        @test isapprox(
            bg_value(columns, "T1/p1.e", t) - bg_value(columns, "T1/n1.e", t),
            n * (bg_value(columns, "T1/p2.e", t) - bg_value(columns, "T1/n2.e", t));
            rtol = 1e-6
        )
        @test isapprox(bg_value(columns, "T1/p2.e", t), v2; rtol = 1e-6)
        @test isapprox(bg_value(columns, "T1/n1.e", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "T1/n2.e", t), 0.0; atol = 1e-12)
        @test isapprox(
            bg_value(columns, "T1/p1.f", t), -bg_value(columns, "T1/p2.f", t) / n;
            rtol = 1e-6, atol = 1e-12
        )
        # The secondary load and the capacitor.
        @test isapprox(bg_value(columns, "T1/p2.f", t), -resistor_current(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "T1/p1.f", t), resistor_current(t) / n;
            rtol = 1e-6)
        @test isapprox(bg_value(columns, "R1/p.f", t), resistor_current(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "K1/v", t), capacitor_voltage(t); rtol = 1e-6)
        # Power: the primary absorbs exactly what the secondary delivers, and the source
        # supplies the primary.
        @test abs(
            bg_value(columns, "T1/p1.P", t) + bg_value(columns, "T1/p2.P", t)
        ) <= 1e-9
        @test isapprox(
            bg_value(columns, "V1/p.P", t) + bg_value(columns, "T1/p1.P", t), 0.0;
            atol = 1e-9
        )
    end

    # The secondary voltage is exactly V/n at t = 0 too (the transformer is algebraic).
    @test isapprox(bg_value(columns, "T1/p2.e", 0.0), v2; rtol = 1e-6)
    # After five time constants the capacitor has settled to 99.3 % of V/n.
    @test bg_value(columns, "K1/v", 5.0e-3) > 0.99 * v2
    @test bg_value(columns, "K1/v", 5.0e-3) < v2
end
