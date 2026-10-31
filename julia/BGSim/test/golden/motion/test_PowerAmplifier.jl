# Golden test for `stdlib:motion/PowerAmplifier`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model A (static sweep): a Ramp command from -1.9 with slope 3.7 drives an amplifier (gain
# 10 V, V_max 12 V, R_out 0.5 Ohm, I_max 3 A, R_limit 100 Ohm) into a 2 Ohm resistor to
# ground (the limits switch at 0.19, 0.31, 0.72 and 0.84 s, off the output grid: a switch
# of a signal comparison on a grid time is the W206 trap of plan/STATUS.md NOTE-6). An
# Integrator on the output current gives the model a state.
# Reference: v_cmd = clamp(10u, -12, 12); inside the current limit i = v_cmd/(R_out + R),
# beyond it the fold-back i = (v_cmd + sign*R_limit*I_max)/(R_out + R_limit + R); v = R*i.
#
# Model B (inductive load): the same amplifier with a constant command 1.2 (12 V, at the
# supply limit) into L = 10 mH in series with 2 Ohm, from rest. The current rises with
# tau1 = L/(R_out + R) towards 4.8 A, reaches I_max = 3 A at t1 = -tau1*ln(1 - 3/4.8), and
# then settles with tau2 = L/(R_out + R_limit + R) at the fold-back current
# (12 + 300)/102.5 A. Both phases are compared with the closed form (rtol 1e-6).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const _PA_PARAMS = Dict{String,Any}("gain" => "10.0", "V_max" => "12.0", "R_out" => "0.5",
    "I_max" => "3.0", "R_limit" => "100.0")

@testset "golden: PowerAmplifier" begin
    @testset "static sweep through the supply and current limits" begin
        nodes = Any[
            bg_node("u", "U", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}("initial" => "-1.9", "slope" => "3.7")),
            bg_node("a", "AMP", bg_ref("stdlib:motion/PowerAmplifier"); params = _PA_PARAMS),
            bg_node("r", "RL", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "2.0")),
            bg_node("g", "G", bg_ref("stdlib:electrical/Ground")),
            bg_node("i", "I", bg_ref("stdlib:continuous/Integrator")),
        ]
        conns = Any[
            bg_conn("c1", "signal", "u", "y", "a", "u"),
            bg_conn("c2", "wire", "a", "p", "r", "p"),
            bg_conn("c3", "wire", "r", "n", "g", "p"),
            bg_conn("c4", "wire", "a", "n", "g", "p"),
            bg_conn("c5", "signal", "a", "i", "i", "u"),
        ]
        columns, result, _ = bg_run(bg_model("AmplifierSweep", nodes, conns; t_end = 1.0,
            points = 201))
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        function ref(t)
            vc = clamp(10.0 * (-1.9 + 3.7t), -12.0, 12.0)
            i = vc / 2.5
            abs(i) > 3.0 && (i = (vc + sign(vc) * 300.0) / 102.5)
            return i, 2.0i
        end
        grid = range(0.0, 1.0; length = 201)
        @test maximum(abs(bg_value(columns, "AMP/i", t) - ref(t)[1]) for t in grid) < 1e-9
        @test maximum(abs(bg_value(columns, "AMP/v", t) - ref(t)[2]) for t in grid) < 1e-9
        # The resistor sees the same current: the sign convention i = -p.f.
        @test maximum(abs(bg_value(columns, "RL/p.f", t) - ref(t)[1]) for t in grid) < 1e-9
        @test bg_value(columns, "AMP/i", 0.0) ≈ -312.0 / 102.5 rtol = 1e-12
        @test bg_value(columns, "AMP/i", 0.5) ≈ ref(0.5)[1] rtol = 1e-12
        @test bg_value(columns, "AMP/i", 1.0) ≈ 312.0 / 102.5 rtol = 1e-12
    end

    @testset "inductive load: rise, then the fold-back current limit" begin
        nodes = Any[
            bg_node("u", "U", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.2")),
            bg_node("a", "AMP", bg_ref("stdlib:motion/PowerAmplifier"); params = _PA_PARAMS),
            bg_node("l", "L1", bg_ref("stdlib:electrical/Inductor");
                params = Dict{String,Any}("L" => "0.01")),
            bg_node("r", "RL", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "2.0")),
            bg_node("g", "G", bg_ref("stdlib:electrical/Ground")),
        ]
        conns = Any[
            bg_conn("c1", "signal", "u", "y", "a", "u"),
            bg_conn("c2", "wire", "a", "p", "l", "p"),
            bg_conn("c3", "wire", "l", "n", "r", "p"),
            bg_conn("c4", "wire", "r", "n", "g", "p"),
            bg_conn("c5", "wire", "a", "n", "g", "p"),
        ]
        columns, result, _ = bg_run(bg_model("AmplifierCurrentLimit", nodes, conns;
            t_end = 0.01, points = 1001))
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        tau1, tau2 = 0.01 / 2.5, 0.01 / 102.5
        t1 = -tau1 * log(1 - 3.0 / 4.8)
        iss = 312.0 / 102.5
        i_ref(t) = t <= t1 ? 4.8 * (1 - exp(-t / tau1)) : iss + (3.0 - iss) * exp(-(t - t1) / tau2)
        grid = range(0.0, 0.01; length = 1001)
        @test maximum(abs(bg_value(columns, "AMP/i", t) - i_ref(t)) for t in grid) < 1e-6
        @test maximum(bg_all(columns, "AMP/i")) <= iss * (1 + 1e-9)
        @test bg_value(columns, "AMP/i", 0.01) ≈ iss rtol = 1e-9
        # The supply limit: the commanded 12 V, minus the drops, is what the load sees.
        @test bg_value(columns, "AMP/v", 0.01) ≈ 12.0 - 0.5iss - 100.0 * (iss - 3.0) rtol = 1e-9
    end
end
