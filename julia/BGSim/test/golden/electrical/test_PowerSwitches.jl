# Golden tests for `stdlib:electrical/MOSFET` and `stdlib:electrical/IGBT`, through the
# real pipeline.
#
# Model: a source V drives a load R_L into the switch (d or c); the switch's other terminal
# (s or e) is grounded. The Bool gate comes from a discrete `Compare` (u1 > u2) on a `Step`
# (0 until 2 ms, 1 after) against 0.5 on its 1 ms clock, so the gate turns on at t = 2 ms.
#
# With v the switch voltage and G_off = 0:
#   MOSFET forward, off:  no current, v = V;
#   MOSFET forward, on:   v = V*R_on/(R_L + R_on), the channel carries V/(R_L + R_on);
#   MOSFET reverse, off:  the body diode conducts, v = (V/R_L - V_f/R_d)/(1/R_L + 1/R_d);
#   MOSFET reverse, on:   the channel conducts backwards (|v| < V_f), v = V*R_on/(R_L + R_on);
#   IGBT forward, on:     v = (V/R_L + V_ce0/R_on)/(1/R_L + 1/R_on), above the knee V_ce0;
#   IGBT reverse, on:     the switch blocks, the freewheeling diode conducts (as MOSFET off).
# Every case dissipates: v times the current into the switch is never negative.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function power_switch_model(block, V)
    hi, lo = block == "MOSFET" ? ("d", "s") : ("c", "e")
    params = Dict{String,Any}("R_on" => "0.05", "G_off" => "0.0", "V_f" => "0.7",
        "R_d" => "0.02")
    block == "IGBT" && (params["V_ce0"] = "1.2")
    return bg_model(
        "Switch$block",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(V))),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource")),
            bg_node("n3", "RL", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "10.0")),
            bg_node("n4", "Q1", bg_ref("stdlib:electrical/" * block); params = params),
            bg_node("n5", "G1", bg_ref("stdlib:electrical/Ground")),
            bg_node("n6", "Step1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => "2.0e-3", "initial" => "0.0",
                    "final" => "1.0")),
            bg_node("n7", "Cmp1", bg_ref("stdlib:discrete/Compare");
                params = Dict{String,Any}("op" => "4")),
            bg_node("n8", "Thr1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.5")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", hi),
            bg_conn("c4", "wire", "n4", lo, "n5", "p"),
            bg_conn("c5", "wire", "n2", "n", "n5", "p"),
            bg_conn("c6", "signal", "n6", "y", "n7", "u1"),
            bg_conn("c7", "signal", "n8", "y", "n7", "u2"),
            bg_conn("c8", "signal", "n7", "y", "n4", "gate"),
        ];
        t_end = 0.004, points = 41, solver = "auto",
    )
end

@testset "golden: MOSFET and IGBT" begin
    R_L = 10.0
    R_on = 0.05
    V_f = 0.7
    R_d = 0.02
    V_ce0 = 1.2
    diode_v(V) = (V / R_L - V_f / R_d) / (1 / R_L + 1 / R_d)
    channel_v(V) = V * R_on / (R_L + R_on)
    igbt_v(V) = (V / R_L + V_ce0 / R_on) / (1 / R_L + 1 / R_on)
    cases = [
        # block, V, v while the gate is off, v while it is on
        ("MOSFET", 12.0, 12.0, channel_v(12.0)),
        ("MOSFET", -12.0, diode_v(-12.0), channel_v(-12.0)),
        ("IGBT", 12.0, 12.0, igbt_v(12.0)),
        ("IGBT", -12.0, diode_v(-12.0), diode_v(-12.0)),
    ]
    for (block, V, v_off, v_on) in cases
        @testset "$block at $V V" begin
            hi = block == "MOSFET" ? "d" : "c"
            columns, result, flat = bg_run(power_switch_model(block, V))
            @test result.status == "done"
            @test isempty([e for e in result.diagnostics if e.severity == "error"])
            @test flat.stats.states == 0
            for (t, v) in ((0.0, v_off), (1.0e-3, v_off), (1.9e-3, v_off), (2.0e-3, v_on),
                (3.0e-3, v_on), (4.0e-3, v_on))
                @test isapprox(bg_value(columns, "Q1/v", t), v; rtol = 1e-9)
                @test isapprox(bg_value(columns, "Q1/$hi.f", t), (V - v) / R_L; rtol = 1e-9,
                    atol = 1e-12)
                # Dissipation: the switch only takes power in.
                @test bg_value(columns, "Q1/$hi.P", t) +
                      bg_value(columns, "Q1/$(block == "MOSFET" ? "s" : "e").P", t) >= -1e-12
            end
            # Which path carries the current.
            if V < 0 && !(block == "MOSFET")
                @test abs(bg_value(columns, "Q1/i_sw", 3.0e-3)) < 1e-12
                @test bg_value(columns, "Q1/i_diode", 3.0e-3) > 0.0
            end
            if block == "MOSFET" && V < 0
                @test bg_value(columns, "Q1/i_diode", 1.0e-3) > 0.0
                @test bg_value(columns, "Q1/i_diode", 3.0e-3) == 0.0
                @test bg_value(columns, "Q1/i_ch", 3.0e-3) < 0.0
            end
        end
    end
end
