# Golden test for `stdlib:electrical/CurrentSource` (plan section 8, M2 row: CurrentSource),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a current source (I = 1 mA, u = 1 from a Constant) drives a node with a 1 kOhm
# resistor and a 1 uF capacitor in parallel to ground. The source's own sign convention is the
# bond-graph one (`p.f = I*u`, flow positive into the port), so p sits at ground and n at the
# driven node; that delivers +I into the node.
#
# Reference: the analytic solution of the parallel RC driven by a current step,
#   v(t) = I*R*(1 - exp(-t/(R*C))),  i_R = v/R,  i_C = I*exp(-t/(R*C)),  tau = 1 ms.
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10), plus
# the port-flow relations of the block and the node power balance.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: CurrentSource" begin
    I = 1.0e-3
    R = 1.0e3
    C = 1.0e-6
    tau = R * C
    voltage(t) = I * R * (1.0 - exp(-t / tau))
    resistor_current(t) = I * (1.0 - exp(-t / tau))
    capacitor_current(t) = I * exp(-t / tau)

    model = bg_model(
        "CurrentSourceDrivesRC",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "I1", bg_ref("stdlib:electrical/CurrentSource");
                params = Dict{String,Any}("I" => "1.0e-3")),
            bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "1.0e3")),
            bg_node("n4", "K1", bg_ref("stdlib:electrical/Capacitor");
                params = Dict{String,Any}("C" => "1.0e-6")),
            bg_node("n5", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "n", "n3", "p"),
            bg_conn("c3", "wire", "n2", "n", "n4", "p"),
            bg_conn("c4", "wire", "n2", "p", "n5", "p"),
            bg_conn("c5", "wire", "n3", "n", "n5", "p"),
            bg_conn("c6", "wire", "n4", "n", "n5", "p"),
        ];
        t_end = 0.005, points = 51,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the capacitor voltage

    for t in (0.0, 2.0e-4, 5.0e-4, 1.0e-3, 2.0e-3, 5.0e-3)
        # The block: p.f = I*u and p.f + n.f = 0, with u = 1.
        @test isapprox(bg_value(columns, "I1/u", t), 1.0; rtol = 1e-6)
        @test isapprox(bg_value(columns, "I1/p.f", t), I; rtol = 1e-6)
        @test isapprox(bg_value(columns, "I1/n.f", t), -I; rtol = 1e-6)
        # The node: the resistor and the capacitor split the imposed current.
        @test isapprox(bg_value(columns, "K1/v", t), voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "R1/p.e", t), voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "R1/p.f", t), resistor_current(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "K1/p.f", t), capacitor_current(t); rtol = 1e-6)
        # KCL at the driven node: R1/p.f + K1/p.f = -I1/n.f (the source's delivered current).
        @test isapprox(
            bg_value(columns, "R1/p.f", t) + bg_value(columns, "K1/p.f", t),
            -bg_value(columns, "I1/n.f", t);
            rtol = 1e-6, atol = 1e-12
        )
        # Power: the source delivers exactly what the resistor dissipates plus what the
        # capacitor stores (all four ports of the two nodes are recorded, D15).
        power(t) =
            bg_value(columns, "I1/p.P", t) + bg_value(columns, "I1/n.P", t) +
            bg_value(columns, "R1/p.P", t) + bg_value(columns, "K1/p.P", t)
        @test abs(power(t)) <= 1e-9
    end

    # The whole recorded grid, not only the sample points.
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "K1/v") .- voltage.(times))) < 1e-9
end
