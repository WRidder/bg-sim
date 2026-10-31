# Golden test for `stdlib:bondgraph/RS`, the resistive source: an R whose dissipated power
# leaves through a Thermal heat port as heat flow.
#
# 1. Electrical adoption. A constant 6 V source is bonded straight to the Generic port of an
#    RS (r = 3); the island adopts Electrical, so r is in Ohm and the bond power is V*A. The
#    heat port charges a heat capacity from T0, which has no other path, so its temperature
#    rises linearly with exactly the dissipated power:
#        p.f = V/r,  heat flow = V^2/r = 12 W,  T(t) = T0 + V^2/(r*C) * t.
# 2. Mechanical adoption. A rotating inertia J spinning down through an RS (a viscous
#    damper, r in N*m*s/rad) on a 1-junction. The kinetic energy it loses arrives as heat:
#        w(t) = w0*exp(-r*t/J),  C*(T(t) - T0) = J/2*(w0^2 - w(t)^2).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: RS" begin
    @testset "electrical: a source bonded to RS heats a capacity linearly" begin
        V, r, C, T0 = 6.0, 3.0, 40.0, 300.0
        model = bg_model(
            "RSElectrical",
            [
                bg_node("n1", "One", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0")),
                bg_node("n2", "Supply", bg_ref("stdlib:electrical/VoltageSource");
                    params = Dict{String,Any}("V" => string(V))),
                bg_node("n3", "Gnd", bg_ref("stdlib:electrical/Ground")),
                bg_node("n4", "Load", bg_ref("stdlib:bondgraph/RS");
                    params = Dict{String,Any}("r" => string(r))),
                bg_node("n5", "Mass", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C)),
                    starts = Dict{String,Any}("T" => string(T0))),
            ],
            [
                bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "wire", "n2", "n", "n3", "p"),
                bg_conn("c3", "bond", "n2", "p", "n4", "p"),
                bg_conn("c4", "wire", "n4", "heat", "n5", "a"),
            ];
            t_end = 10.0, points = 11,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        # The resistive port adopted Electrical (r in Ohm); the heat port stayed Thermal.
        r_param = only(p for p in flat.parameters if p.id == "Load/r")
        @test r_param.unit == BGSim.Units.parse_unit("Ohm")
        for t in (0.0, 2.0, 5.0, 10.0)
            @test isapprox(bg_value(columns, "Load/p.e", t), V; rtol = 1e-12)
            @test isapprox(bg_value(columns, "Load/P", t), V^2 / r; rtol = 1e-12)
            @test isapprox(bg_value(columns, "Load/heat.f", t), -V^2 / r; rtol = 1e-12)
            # The Generic port's bond power (V*A) is exactly the heat flow.
            @test isapprox(bg_value(columns, "Load/p.P", t), -bg_value(columns, "Load/heat.f", t);
                rtol = 1e-12)
            @test isapprox(bg_value(columns, "Mass/T", t), T0 + V^2 / (r * C) * t; rtol = 1e-10)
        end
    end

    @testset "rotation: an inertia spinning down through RS" begin
        J, r, w0 = 0.02, 0.01, 100.0
        C, T0 = 5.0, 300.0
        tau = J / r
        model = bg_model(
            "RSRotation",
            [
                bg_node("n1", "Rotor", bg_ref("stdlib:rotation/Inertia");
                    params = Dict{String,Any}("J" => string(J)),
                    starts = Dict{String,Any}("w" => string(w0))),
                bg_node("n2", "Frame", bg_ref("stdlib:rotation/FixedShaft")),
                bg_node("n3", "Drag", bg_ref("stdlib:bondgraph/RS");
                    params = Dict{String,Any}("r" => string(r))),
                bg_node("n4", "Mass", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C)),
                    starts = Dict{String,Any}("T" => string(T0))),
            ],
            [
                bg_conn("c1", "wire", "n1", "b", "n2", "a"),
                bg_conn("c2", "bond", "n1", "a", "n3", "p"),
                bg_conn("c3", "wire", "n3", "heat", "n4", "a"),
            ];
            t_end = 6.0, points = 61,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        r_param = only(p for p in flat.parameters if p.id == "Drag/r")
        @test r_param.unit == BGSim.Units.parse_unit("N*m*s/rad")
        for t in (0.0, 1.0, 2.0, 4.0, 6.0)
            w = w0 * exp(-t / tau)
            @test isapprox(bg_value(columns, "Rotor/w", t), w; rtol = 1e-7)
            heat = C * (bg_value(columns, "Mass/T", t) - T0)
            @test isapprox(heat, J / 2 * (w0^2 - w^2); rtol = 1e-7, atol = 1e-8)
        end
    end
end
