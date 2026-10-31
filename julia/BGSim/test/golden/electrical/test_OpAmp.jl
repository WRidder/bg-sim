# Golden test for `stdlib:electrical/OpAmp`, through the real pipeline.
#
# Inverting amplifier: a source V_in feeds R1 into the inverting input in_n, Rf feeds back
# from out to in_n, in_p is grounded and a load R_L hangs on the output.
#   * ideal (constant ideal = 1): v_out = -Rf/R1 * V_in, in_n is a virtual ground;
#   * finite gain A (ideal = 0): after the output lag T_o (1 us) has settled,
#     v_out = -A*Rf*V_in/(R1 + Rf + A*R1), limited to the rails;
#     saturated, v_out = V_neg (or V_pos) and v_n = (V_in*Rf + v_out*R1)/(R1 + Rf).
# No current enters either input; the output current is v_out/R_L + (v_out - v_n)/Rf.
#
# Integrator: the same circuit with a capacitor C in place of Rf. The ideal op-amp holds
# in_n at 0 V, so the input current V_in/R charges C and v_out = -V_in*t/(R*C).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function opamp_node(id, name, ideal; params = Dict{String,Any}())
    node = bg_node(id, name, bg_ref("stdlib:electrical/OpAmp"); params = params)
    node["constants"] = Dict{String,Any}("ideal" => ideal)
    return node
end

function opamp_inverting_model(V_in, ideal; feedback = "Resistor", t_end = 0.01, points = 11)
    fb_params = feedback == "Resistor" ? Dict{String,Any}("R" => "4.7e4") :
                Dict{String,Any}("C" => "1.0e-6")
    return bg_model(
        "OpAmpInverting",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(V_in))),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource")),
            bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "1.0e4")),
            bg_node("n4", "Rf", bg_ref("stdlib:electrical/" * feedback); params = fb_params),
            opamp_node("n5", "OA1", ideal; params = Dict{String,Any}("A" => "1.0e3",
                "V_pos" => "12.0", "V_neg" => "-10.0")),
            bg_node("n6", "RL", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => "2.0e3")),
            bg_node("n7", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n5", "in_n"),
            bg_conn("c4", "wire", "n5", "in_n", "n4", "p"),
            bg_conn("c5", "wire", "n4", "n", "n5", "out"),
            bg_conn("c6", "wire", "n5", "out", "n6", "p"),
            bg_conn("c7", "wire", "n6", "n", "n7", "p"),
            bg_conn("c8", "wire", "n5", "in_p", "n7", "p"),
            bg_conn("c9", "wire", "n2", "n", "n7", "p"),
        ];
        t_end = t_end, points = points,
    )
end

@testset "golden: OpAmp" begin
    R1 = 1.0e4
    Rf = 4.7e4
    R_L = 2.0e3
    A = 1.0e3

    # Ideal: the gain is exactly -Rf/R1 and in_n is a virtual ground.
    V_in = 0.5
    columns, result, flat = bg_run(opamp_inverting_model(V_in, 1))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    v_out = -Rf / R1 * V_in
    for t in (0.0, 0.01)
        @test isapprox(bg_value(columns, "OA1/out.e", t), v_out; rtol = 1e-9)
        @test abs(bg_value(columns, "OA1/in_n.e", t)) < 1e-12
        @test bg_value(columns, "OA1/in_p.f", t) == 0.0
        @test abs(bg_value(columns, "OA1/in_n.f", t)) < 1e-15
        @test isapprox(bg_value(columns, "R1/p.f", t), V_in / R1; rtol = 1e-9)
        # The output sources the load current and the feedback current.
        @test isapprox(bg_value(columns, "OA1/out.f", t), -(v_out / R_L - V_in / R1);
            rtol = 1e-9)
    end

    # Finite gain, linear: the closed-loop gain is slightly below Rf/R1.
    columns, result, flat = bg_run(opamp_inverting_model(V_in, 0))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    v_out = -A * Rf * V_in / (R1 + Rf + A * R1)
    v_n = (V_in * Rf + v_out * R1) / (R1 + Rf)
    for t in (0.005, 0.01)
        @test isapprox(bg_value(columns, "OA1/out.e", t), v_out; rtol = 1e-9)
        @test isapprox(bg_value(columns, "OA1/in_n.e", t), v_n; rtol = 1e-9)
        @test isapprox(bg_value(columns, "OA1/out.e", t), -A * v_n; rtol = 1e-9)
    end

    # Finite gain, saturated at both rails.
    for (V_in, rail) in ((5.0, -10.0), (-5.0, 12.0))
        columns, result, flat = bg_run(opamp_inverting_model(V_in, 0))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        v_n = (V_in * Rf + rail * R1) / (R1 + Rf)
        for t in (0.005, 0.01)
            @test isapprox(bg_value(columns, "OA1/out.e", t), rail; rtol = 1e-9)
            @test isapprox(bg_value(columns, "OA1/in_n.e", t), v_n; rtol = 1e-9)
        end
    end

    # Ideal integrator: a capacitor in the feedback path.
    V_in = 0.2
    C = 1.0e-6
    columns, result, flat = bg_run(opamp_inverting_model(V_in, 1; feedback = "Capacitor",
        t_end = 0.1, points = 11))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 2                 # the capacitor and the unused v_o
    for t in (0.0, 0.05, 0.1)
        @test isapprox(bg_value(columns, "OA1/out.e", t), -V_in * t / (R1 * C);
            rtol = 1e-6, atol = 1e-12)
        @test abs(bg_value(columns, "OA1/in_n.e", t)) < 1e-12
    end
end
