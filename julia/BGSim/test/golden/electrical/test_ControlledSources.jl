# Golden tests for the controlled sources `stdlib:electrical/VCVS`, `VCCS`, `CCVS` and
# `CCCS`, through the real pipeline.
#
# Voltage control: a 2 V source sits directly across the controlling side p1-n1 (an open
# circuit, so p1.f = 0 exactly).
# Current control: the 2 V source drives the controlling side through R_s = 1 kOhm (the
# controlling side is a short, so i1 = 2 mA and v1 = 0).
# The controlled side p2-n2 feeds a load R_L = 500 Ohm to ground (n2 grounded):
#   VCVS: v2 = gain*v1,                     CCVS: v2 = transresistance*i1,
#   VCCS: p2.f = g*v1, so v2 = -g*v1*R_L,   CCCS: p2.f = gain*i1, so v2 = -gain*i1*R_L.
# The controlled side delivers the load power v2^2/R_L (p2.P = -v2^2/R_L).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function controlled_source_model(block, param, value; current_control)
    nodes = Any[
        bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "2.0")),
        bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource")),
        bg_node("n3", "S1", bg_ref("stdlib:electrical/" * block);
            params = Dict{String,Any}(param => string(value))),
        bg_node("n4", "RL", bg_ref("stdlib:electrical/Resistor");
            params = Dict{String,Any}("R" => "500.0")),
        bg_node("n5", "G1", bg_ref("stdlib:electrical/Ground")),
        bg_node("n6", "Rs", bg_ref("stdlib:electrical/Resistor");
            params = Dict{String,Any}("R" => "1000.0")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "wire", "n2", "n", "n5", "p"),
        bg_conn("c4", "wire", "n3", "n1", "n5", "p"),
        bg_conn("c5", "wire", "n3", "p2", "n4", "p"),
        bg_conn("c6", "wire", "n4", "n", "n5", "p"),
        bg_conn("c7", "wire", "n3", "n2", "n5", "p"),
    ]
    if current_control
        push!(conns, bg_conn("c3", "wire", "n2", "p", "n6", "p"))
        push!(conns, bg_conn("c8", "wire", "n6", "n", "n3", "p1"))
    else
        push!(conns, bg_conn("c3", "wire", "n2", "p", "n3", "p1"))
        # The unused series resistor shorted to ground, so the model stays well posed.
        push!(conns, bg_conn("c8", "wire", "n6", "p", "n5", "p"))
        push!(conns, bg_conn("c9", "wire", "n6", "n", "n5", "p"))
    end
    return bg_model("Controlled$block", nodes, conns; t_end = 0.01, points = 11)
end

@testset "golden: controlled sources" begin
    V = 2.0
    R_L = 500.0
    R_s = 1000.0
    i1 = V / R_s
    cases = [
        ("VCVS", "gain", 3.0, false, 3.0 * V),
        ("VCCS", "transconductance", 0.01, false, -0.01 * V * R_L),
        ("CCVS", "transresistance", 2500.0, true, 2500.0 * i1),
        ("CCCS", "gain", 4.0, true, -4.0 * i1 * R_L),
    ]
    for (block, param, value, current_control, v2) in cases
        @testset "$block" begin
            columns, result, flat = bg_run(controlled_source_model(block, param, value;
                current_control))
            @test result.status == "done"
            @test isempty([e for e in result.diagnostics if e.severity == "error"])
            @test flat.stats.states == 0
            for t in (0.0, 0.01)
                @test isapprox(bg_value(columns, "S1/p2.e", t) - bg_value(columns, "S1/n2.e", t),
                    v2; rtol = 1e-9)
                @test isapprox(bg_value(columns, "RL/p.f", t), v2 / R_L; rtol = 1e-9)
                @test isapprox(bg_value(columns, "S1/p2.f", t), -v2 / R_L; rtol = 1e-9)
                @test isapprox(bg_value(columns, "S1/p2.P", t) + bg_value(columns, "S1/n2.P", t),
                    -v2^2 / R_L; rtol = 1e-9)
                if current_control
                    # A short: no voltage over the controlling side, the full current i1.
                    @test abs(bg_value(columns, "S1/p1.e", t) - bg_value(columns, "S1/n1.e", t)) <
                          1e-12
                    @test isapprox(bg_value(columns, "S1/p1.f", t), i1; rtol = 1e-9)
                else
                    # An open circuit: the full voltage, no current.
                    @test isapprox(bg_value(columns, "S1/p1.e", t), V; rtol = 1e-9)
                    @test bg_value(columns, "S1/p1.f", t) == 0.0
                end
            end
        end
    end
end
