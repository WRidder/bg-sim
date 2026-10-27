# Golden test for `stdlib:electrical/IdealDiode` (plan section 8, M2 row: Ideal diode),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a DC voltage source drives a 1 kOhm resistor into a node with a 1 uF capacitor to
# ground and the diode from that node to ground (a shunt clipper). `R_on = 100 Ohm`,
# `V_knee = 0.7 V` and `G_off = 0` (an ideal open circuit), so both branches are exactly
# piecewise linear. The diode's `ifelse` condition is `v - V_knee`, so J2.3's switch collector
# lands the run on the knee crossing; the analytic reference then covers both states:
#
#   * off (t <= t1):  v(t) = V*(1 - exp(-t/(R*C))),  i_d = 0;
#   * on  (t > t1):   v(t) = v_eq + (V_knee - v_eq)*exp(-(t - t1)/tau2), with
#                     v_eq = (V/R + V_knee/R_on)/(1/R + 1/R_on), tau2 = C/(1/R + 1/R_on),
#                     t1 = -R*C*ln(1 - V_knee/V), and i_d = (v - V_knee)/R_on.
#
# The reverse model (V = -10 V) keeps the diode off for the whole run and gives the plain RC
# curve. Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function diode_model(source::String)
    return bg_model(
        "DiodeShuntClipper",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => source)),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => "1.0")),
            bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "1.0e3")),
            bg_node("n4", "K1", bg_ref("stdlib:electrical/Capacitor");
                params = Dict{String,Any}("C" => "1.0e-6")),
            bg_node("n5", "D1", bg_ref("stdlib:electrical/IdealDiode");
                params = Dict{String,Any}("R_on" => "100.0", "G_off" => "0.0",
                    "V_knee" => "0.7")),
            bg_node("n6", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", "p"),
            bg_conn("c4", "wire", "n4", "p", "n5", "p"),
            bg_conn("c5", "wire", "n2", "n", "n6", "p"),
            bg_conn("c6", "wire", "n4", "n", "n6", "p"),
            bg_conn("c7", "wire", "n5", "n", "n6", "p"),
        ];
        t_end = 0.002, points = 101, solver = "auto",
    )
end

@testset "golden: IdealDiode" begin
    V = 10.0
    R = 1.0e3
    C = 1.0e-6
    R_on = 100.0
    V_knee = 0.7
    tau1 = R * C
    t1 = -tau1 * log(1.0 - V_knee / V)
    v_eq = (V / R + V_knee / R_on) / (1.0 / R + 1.0 / R_on)
    tau2 = C / (1.0 / R + 1.0 / R_on)
    voltage(t) = t <= t1 ? V * (1.0 - exp(-t / tau1)) :
                 v_eq + (V_knee - v_eq) * exp(-(t - t1) / tau2)
    diode_current(t) = t <= t1 ? 0.0 : (voltage(t) - V_knee) / R_on
    resistor_current(t) = (V - voltage(t)) / R
    capacitor_current(t) = resistor_current(t) - diode_current(t)

    forward = bg_run(diode_model("10.0"))
    columns, result, flat = forward
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the capacitor voltage
    @test 0.0 < t1 < 1.0e-4                      # the knee crossing is inside the run

    for t in (2.0e-5, 6.0e-5, 8.0e-5, 1.0e-4, 2.0e-4, 4.0e-4, 1.0e-3, 2.0e-3)
        @test isapprox(bg_value(columns, "K1/v", t), voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "D1/p.e", t), voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "R1/p.e", t), V; rtol = 1e-6)
        @test isapprox(bg_value(columns, "R1/p.f", t), resistor_current(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "D1/p.f", t), diode_current(t); rtol = 1e-6,
            atol = 1e-12)
        @test isapprox(bg_value(columns, "K1/p.f", t), capacitor_current(t); rtol = 1e-6,
            atol = 1e-12)
        # KCL at the clipper node: what the resistor feeds in leaves through C and the diode.
        @test isapprox(
            bg_value(columns, "K1/p.f", t) + bg_value(columns, "D1/p.f", t),
            resistor_current(t);
            rtol = 1e-6, atol = 1e-12
        )
    end

    # Before the knee the diode is an open circuit; after it the current really flows.
    @test bg_value(columns, "D1/p.f", 6.0e-5) == 0.0
    @test bg_value(columns, "D1/p.f", 2.0e-3) > 0.0
    @test isapprox(bg_value(columns, "K1/v", 2.0e-3), v_eq; rtol = 1e-6)

    # Reverse bias: V = -10 V, the diode stays off (G_off = 0) and the node follows the RC
    # charge toward the source, so the recorded current through the diode is exactly zero.
    rev_columns, rev_result, rev_flat = bg_run(diode_model("-10.0"))
    @test rev_result.status == "done"
    @test isempty([d for d in rev_result.diagnostics if d.severity == "error"])
    @test rev_flat.stats.states == 1
    reverse_voltage(t) = -V * (1.0 - exp(-t / tau1))
    for t in (2.0e-5, 2.0e-4, 1.0e-3, 2.0e-3)
        @test isapprox(bg_value(rev_columns, "K1/v", t), reverse_voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(rev_columns, "D1/p.e", t), reverse_voltage(t); rtol = 1e-6)
        @test bg_value(rev_columns, "D1/p.f", t) == 0.0
        @test isapprox(bg_value(rev_columns, "R1/p.f", t),
            (-V - reverse_voltage(t)) / R; rtol = 1e-6)
    end
end
