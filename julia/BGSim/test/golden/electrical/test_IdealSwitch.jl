# Golden test for `stdlib:electrical/IdealSwitch` (plan section 8, M2 row: Ideal switch),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a 10 V source drives a 1 kOhm resistor into a node with a 1 uF capacitor to ground
# and the switch from that node to ground (`R_on = 100 Ohm`, `G_off = 0`). The switch's Bool
# `ctrl` comes from a discrete `Compare` (`u1 > u2`) that samples a `Step` (0 V until 2 ms,
# 1 V after) and a Constant 0.55 on its 1 ms clock. The first tick that sees the step high is
# exactly t = 2 ms, so the switch closes there.
#
# Reference: the analytic solution of the two linear states, with t_on = 2 ms:
#   * open (t < t_on):   v(t) = V*(1 - exp(-t/(R*C)));
#   * closed (t >= t_on): v(t) = v_eq + (v(t_on) - v_eq)*exp(-(t - t_on)/tau_on), with
#                         v_eq = V*R_on/(R + R_on),  tau_on = C*R*R_on/(R + R_on),
#                         switch current v/R_on.
# The run records the tick as a left and a right row at the same t; `bg_value` returns the
# right limit, which is the state just after the switch closed.
#
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: IdealSwitch" begin
    V = 10.0
    R = 1.0e3
    C = 1.0e-6
    R_on = 100.0
    t_on = 2.0e-3
    tau_off = R * C
    tau_on = C * R * R_on / (R + R_on)
    v_eq = V * R_on / (R + R_on)
    v_open(t) = V * (1.0 - exp(-t / tau_off))
    v_closed(t) = v_eq + (v_open(t_on) - v_eq) * exp(-(t - t_on) / tau_on)
    voltage(t) = t < t_on ? v_open(t) : v_closed(t)
    switch_current(t) = t < t_on ? 0.0 : voltage(t) / R_on
    resistor_current(t) = (V - voltage(t)) / R
    capacitor_current(t) = resistor_current(t) - switch_current(t)

    model = bg_model(
        "IdealSwitchChargesC",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "10.0")),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => "1.0")),
            bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "1.0e3")),
            bg_node("n4", "K1", bg_ref("stdlib:electrical/Capacitor");
                params = Dict{String,Any}("C" => "1.0e-6")),
            bg_node("n5", "S1", bg_ref("stdlib:electrical/IdealSwitch");
                params = Dict{String,Any}("R_on" => "100.0", "G_off" => "0.0")),
            bg_node("n6", "G1", bg_ref("stdlib:electrical/Ground")),
            bg_node("n7", "Step1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => "2.0e-3", "initial" => "0.0",
                    "final" => "1.0")),
            bg_node("n8", "Cmp1", bg_ref("stdlib:discrete/Compare");
                params = Dict{String,Any}("op" => "4")),
            bg_node("n9", "Thr1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.55")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", "p"),
            bg_conn("c4", "wire", "n4", "p", "n5", "p"),
            bg_conn("c5", "wire", "n2", "n", "n6", "p"),
            bg_conn("c6", "wire", "n4", "n", "n6", "p"),
            bg_conn("c7", "wire", "n5", "n", "n6", "p"),
            bg_conn("c8", "signal", "n7", "y", "n8", "u1"),
            bg_conn("c9", "signal", "n9", "y", "n8", "u2"),
            bg_conn("c10", "signal", "n8", "y", "n5", "ctrl"),
        ];
        t_end = 0.006, points = 601, solver = "auto",
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the capacitor voltage

    # The control: false before the tick at 2 ms, true from it on.
    for t in (0.0, 5.0e-4, 1.0e-3, 1.9e-3)
        @test bg_value(columns, "S1/ctrl", t) == 0.0
        @test bg_value(columns, "Cmp1/y", t) == 0.0
    end
    for t in (t_on, 2.05e-3, 3.0e-3, 6.0e-3)
        @test bg_value(columns, "S1/ctrl", t) == 1.0
        @test bg_value(columns, "Cmp1/y", t) == 1.0
    end

    for t in (5.0e-4, 1.0e-3, 1.9e-3, t_on, 2.05e-3, 2.2e-3, 3.0e-3, 6.0e-3)
        @test isapprox(bg_value(columns, "K1/v", t), voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "S1/p.e", t), voltage(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "R1/p.f", t), resistor_current(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "S1/p.f", t), switch_current(t); rtol = 1e-6,
            atol = 1e-12)
        @test isapprox(bg_value(columns, "K1/p.f", t), capacitor_current(t); rtol = 1e-6,
            atol = 1e-12)
        # KCL at the switched node.
        @test isapprox(
            bg_value(columns, "K1/p.f", t) + bg_value(columns, "S1/p.f", t),
            resistor_current(t);
            rtol = 1e-6, atol = 1e-12
        )
    end

    # Closed is really closed: the node is pulled to the divider value.
    @test isapprox(bg_value(columns, "K1/v", 6.0e-3), v_eq; rtol = 1e-6)
    @test bg_value(columns, "K1/v", 6.0e-3) < 1.0
end
