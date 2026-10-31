# Golden test for `stdlib:motion/HBridge`, through the real pipeline (`parse` -> `flatten`
# -> `lower` -> `simulate`).
#
# Model A (averaged, resistive): a 24 V bus (VoltageSource) feeds the bridge (R_on 0.01 Ohm)
# whose output drives 4 Ohm; the duty is a Ramp from -1.5 with slope 3 (clamped to -1..1).
# Reference: d = clamp(duty, -1, 1), i = 24 d/(R_on + 4), v_out = 4 i, i_dc = d i, and the
# power balance 24 i_dc = v_out i + R_on i^2 (the bridge only dissipates in R_on).
#
# Model B (switched, inductive): the same bridge driven by a bipolar PWM (low -1, high 1,
# 50 Hz, duty 0.75) into L = 50 mH in series with 4 Ohm. The mean output voltage is
# (2*0.75 - 1)*24 = 12 V, so in the periodic steady state the mean current over whole
# periods is 12/(4 + R_on) A exactly; the current is continuous at every switching edge.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _hbridge_nodes(duty_nodes, duty_conn, load_nodes, load_conns)
    nodes = Any[
        bg_node("vb", "VBUS", bg_ref("stdlib:electrical/VoltageSource");
            params = Dict{String,Any}("V" => "24.0")),
        bg_node("one", "ONE", bg_ref("stdlib:sources/Constant")),
        bg_node("h", "HB", bg_ref("stdlib:motion/HBridge")),
        bg_node("g", "G", bg_ref("stdlib:electrical/Ground")),
        bg_node("ii", "II", bg_ref("stdlib:continuous/Integrator")),
        duty_nodes..., load_nodes...,
    ]
    conns = Any[
        bg_conn("c1", "signal", "one", "y", "vb", "u"),
        bg_conn("c2", "wire", "vb", "p", "h", "dc_p"),
        bg_conn("c3", "wire", "vb", "n", "g", "p"),
        bg_conn("c4", "wire", "h", "dc_n", "g", "p"),
        bg_conn("c5", "wire", "h", "out_n", "g", "p"),
        bg_conn("c6", "signal", "h", "i", "ii", "u"),
        duty_conn, load_conns...,
    ]
    return nodes, conns
end

@testset "golden: HBridge" begin
    @testset "averaged, resistive load" begin
        nodes, conns = _hbridge_nodes(
            [bg_node("d", "DUTY", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}("initial" => "-1.5", "slope" => "3.0"))],
            bg_conn("cd", "signal", "d", "y", "h", "duty"),
            [bg_node("r", "RL", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "4.0"))],
            [bg_conn("cl1", "wire", "h", "out_p", "r", "p"), bg_conn("cl2", "wire", "r", "n", "g", "p")],
        )
        columns, result, _ = bg_run(bg_model("HBridgeAveraged", nodes, conns; t_end = 1.0,
            points = 201))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        grid = range(0.0, 1.0; length = 201)
        d(t) = clamp(-1.5 + 3.0t, -1.0, 1.0)
        i(t) = 24.0 * d(t) / 4.01
        @test maximum(abs(bg_value(columns, "HB/i", t) - i(t)) for t in grid) < 1e-9
        @test maximum(abs(bg_value(columns, "HB/i_dc", t) - d(t) * i(t)) for t in grid) < 1e-9
        @test maximum(abs(bg_value(columns, "RL/p.f", t) - i(t)) for t in grid) < 1e-9
        for t in grid
            ib, idc = bg_value(columns, "HB/i", t), bg_value(columns, "HB/i_dc", t)
            @test 24.0 * idc ≈ 4.0 * ib^2 + 0.01 * ib^2 atol = 1e-9
        end
        @test bg_value(columns, "HB/i", 0.0) ≈ -24.0 / 4.01 rtol = 1e-12
        @test bg_value(columns, "HB/i", 1.0) ≈ 24.0 / 4.01 rtol = 1e-12
    end

    @testset "switched by a bipolar PWM, inductive load" begin
        nodes, conns = _hbridge_nodes(
            [bg_node("dc", "D", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.75")),
             bg_node("pw", "PWM1", bg_ref("stdlib:motion/PWM");
                params = Dict{String,Any}("frequency" => "50.0", "low" => "-1.0", "high" => "1.0"))],
            bg_conn("cd", "signal", "pw", "y", "h", "duty"),
            [bg_node("l", "L1", bg_ref("stdlib:electrical/Inductor");
                params = Dict{String,Any}("L" => "0.05")),
             bg_node("r", "RL", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "4.0"))],
            [bg_conn("cp", "signal", "dc", "y", "pw", "u"),
             bg_conn("cl1", "wire", "h", "out_p", "l", "p"),
             bg_conn("cl2", "wire", "l", "n", "r", "p"),
             bg_conn("cl3", "wire", "r", "n", "g", "p")],
        )
        columns, result, _ = bg_run(bg_model("HBridgeSwitched", nodes, conns; t_end = 1.0,
            points = 1001))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test !any(e -> e.code == "W206", result.diagnostics)
        # The mean current over the last 25 periods (0.5 .. 1.0 s): the integral of i.
        mean_i = (bg_value(columns, "II/y", 1.0) - bg_value(columns, "II/y", 0.5)) / 0.5
        @test mean_i ≈ 12.0 / 4.01 rtol = 1e-5
        # The inductor current is continuous at the edges; the output voltage switches
        # between +24 and -24 V minus the drop over R_on.
        times = columns["time"]
        ib = columns["HB/i"]
        jumps = [abs(ib[k + 1] - ib[k]) for k in 1:length(times) - 1 if times[k + 1] == times[k]]
        @test !isempty(jumps)
        @test maximum(jumps) < 1e-9
        v = columns["HB/out_p.e"]
        @test 23.9 < maximum(v) < 24.1
        @test -24.1 < minimum(v) < -23.9
    end
end
