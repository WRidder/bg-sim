# Golden test for `stdlib:thermal/ResistorHeated`: the electro-thermal energy balance.
#
# A 10 V source drives a heated resistor R(T) = R0*(1 + alpha*(T - T0)) to ground. Its heat
# port feeds a winding capacity C, which loses heat through a conductance G to an ambient at
# T0. Two series heat flow sensors measure the heat leaving the resistor (= the dissipated
# electrical power v*i) and the heat conducted to the ambient, and two integrators turn them
# into energies. The first law of the winding node then holds at every instant:
#
#     E_dissipated(t) = C*(T(t) - T(0)) + E_conducted(t)
#
# and the steady state solves G*(T - T0) = V^2 / (R0*(1 + alpha*(T - T0))), a quadratic in
# dT = T - T0:  G*dT*(1 + alpha*dT) = V^2/R0.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ResistorHeated" begin
    V = 10.0
    R0, alpha, T0 = 5.0, 0.004, 293.15
    C, G = 50.0, 0.5

    model = bg_model(
        "HeatedResistorBalance",
        [
            bg_node("n1", "One", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "Supply", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => string(V))),
            bg_node("n3", "Heater", bg_ref("stdlib:thermal/ResistorHeated");
                params = Dict{String,Any}("R0" => string(R0), "alpha" => string(alpha),
                    "T0" => string(T0))),
            bg_node("n4", "Gnd", bg_ref("stdlib:electrical/Ground")),
            bg_node("n5", "Qloss", bg_ref("stdlib:thermal/HeatFlowSensor")),
            bg_node("n6", "Winding", bg_ref("stdlib:thermal/HeatCapacitor");
                params = Dict{String,Any}("C" => string(C)),
                starts = Dict{String,Any}("T" => string(T0))),
            bg_node("n7", "Qcond", bg_ref("stdlib:thermal/HeatFlowSensor")),
            bg_node("n8", "Path", bg_ref("stdlib:thermal/ThermalConductor");
                params = Dict{String,Any}("G" => string(G))),
            bg_node("n9", "Ambient", bg_ref("stdlib:thermal/FixedTemperature");
                params = Dict{String,Any}("T" => string(T0))),
            bg_node("n10", "Eloss", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n11", "Econd", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", "p"),
            bg_conn("c4", "wire", "n2", "n", "n4", "p"),
            bg_conn("c5", "wire", "n3", "heat", "n5", "a"),
            bg_conn("c6", "wire", "n5", "b", "n6", "a"),
            bg_conn("c7", "wire", "n6", "a", "n7", "a"),
            bg_conn("c8", "wire", "n7", "b", "n8", "a"),
            bg_conn("c9", "wire", "n8", "b", "n9", "a"),
            bg_conn("c10", "signal", "n5", "y", "n10", "u"),
            bg_conn("c11", "signal", "n7", "y", "n11", "u"),
        ];
        t_end = 1000.0, points = 201,
    )
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 3        # winding temperature and the two energy integrals

    for t in (0.0, 5.0, 50.0, 200.0, 1000.0)
        T = bg_value(columns, "Winding/T", t)
        R = R0 * (1 + alpha * (T - T0))
        # The resistance follows the heat port temperature and Ohm's law holds.
        @test isapprox(bg_value(columns, "Heater/R", t), R; rtol = 1e-10)
        @test isapprox(bg_value(columns, "Heater/i", t), V / R; rtol = 1e-9)
        # All of v*i leaves through the heat port: the series sensor reads it exactly.
        @test isapprox(bg_value(columns, "Qloss/y", t), V^2 / R; rtol = 1e-9)
        @test isapprox(bg_value(columns, "Heater/P", t), V^2 / R; rtol = 1e-9)
        @test isapprox(bg_value(columns, "Heater/heat.f", t), -V^2 / R; rtol = 1e-9)
        # First law of the winding node.
        e_loss = bg_value(columns, "Eloss/y", t)
        e_cond = bg_value(columns, "Econd/y", t)
        stored = C * (T - T0)
        @test isapprox(e_loss, stored + e_cond; rtol = 1e-7, atol = 1e-7)
    end
    @test bg_value(columns, "Eloss/y", 1000.0) > 1.0e4       # the balance is not trivial

    # Steady state: G*dT*(1 + alpha*dT) = V^2/R0 (1000 s is 10 time constants C/G... plus the
    # slower drift from the rising resistance, so compare loosely against the root).
    a, b, c = G * alpha, G, -V^2 / R0
    dT = (-b + sqrt(b^2 - 4 * a * c)) / (2 * a)
    @test isapprox(bg_value(columns, "Winding/T", 1000.0) - T0, dT; rtol = 1e-4)
end
