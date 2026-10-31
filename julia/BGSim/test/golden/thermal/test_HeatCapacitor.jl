# Golden tests for `stdlib:thermal/HeatCapacitor`, `ThermalConductor`, `FixedTemperature`
# and `FixedHeatFlow` (the Thermal domain), through the real pipeline.
#
# Thermal convention (spec, "Thermal convention"): a pseudo bond graph, `e` = absolute
# temperature [K] (the across variable), `f` = heat flow [W] into the element.
#
# 1. Newton cooling. A body C at T0 = 400 K, a conductance G to an ambient of Ta = 300 K:
#        T(t) = Ta + (T0 - Ta) * exp(-t/tau),   tau = C/G.
#    The heat that left the body equals the heat the conductor carried:
#        C*(T0 - T(t)) = integral_0^t G*(T - Ta) dt = G*(T0 - Ta)*tau*(1 - exp(-t/tau)).
# 2. First-order heating. The same body starting at Ta, a constant heat flow Q injected:
#        T(t) = Ta + Q/G * (1 - exp(-t/tau)).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: HeatCapacitor" begin
    C = 100.0
    G = 2.0
    Ta = 300.0
    tau = C / G

    @testset "Newton cooling through a ThermalConductor" begin
        T0 = 400.0
        model = bg_model(
            "NewtonCooling",
            [
                bg_node("n1", "Body", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C)),
                    starts = Dict{String,Any}("T" => string(T0))),
                bg_node("n2", "Cond", bg_ref("stdlib:thermal/ThermalConductor");
                    params = Dict{String,Any}("G" => string(G))),
                bg_node("n3", "Ambient", bg_ref("stdlib:thermal/FixedTemperature");
                    params = Dict{String,Any}("T" => string(Ta))),
            ],
            [
                bg_conn("c1", "wire", "n1", "a", "n2", "a"),
                bg_conn("c2", "wire", "n2", "b", "n3", "a"),
            ];
            t_end = 200.0, points = 201,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 1
        for t in (0.0, 10.0, 50.0, 120.0, 200.0)
            T = Ta + (T0 - Ta) * exp(-t / tau)
            @test isapprox(bg_value(columns, "Body/T", t), T; rtol = 1e-8)
            @test isapprox(bg_value(columns, "Body/a.e", t), T; rtol = 1e-8)
            # The conductor carries G*(T - Ta) from the body to the ambient.
            @test isapprox(bg_value(columns, "Cond/Q", t), G * (T - Ta); rtol = 1e-7, atol = 1e-9)
            @test isapprox(bg_value(columns, "Body/a.f", t), -G * (T - Ta); rtol = 1e-7, atol = 1e-9)
            # Heat balance: what the body lost is the integral of the conducted heat flow.
            lost = C * (T0 - bg_value(columns, "Body/T", t))
            conducted = G * (T0 - Ta) * tau * (1 - exp(-t / tau))
            @test isapprox(lost, conducted; rtol = 1e-7, atol = 1e-7)
        end
    end

    @testset "first-order heating from a FixedHeatFlow" begin
        Q = 50.0
        model = bg_model(
            "FirstOrderHeating",
            [
                bg_node("n1", "Body", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C)),
                    starts = Dict{String,Any}("T" => string(Ta))),
                bg_node("n2", "Cond", bg_ref("stdlib:thermal/ThermalConductor");
                    params = Dict{String,Any}("G" => string(G))),
                bg_node("n3", "Ambient", bg_ref("stdlib:thermal/FixedTemperature");
                    params = Dict{String,Any}("T" => string(Ta))),
                bg_node("n4", "Heater", bg_ref("stdlib:thermal/FixedHeatFlow");
                    params = Dict{String,Any}("Q" => string(Q))),
            ],
            [
                bg_conn("c1", "wire", "n1", "a", "n2", "a"),
                bg_conn("c2", "wire", "n2", "b", "n3", "a"),
                bg_conn("c3", "wire", "n4", "a", "n1", "a"),
            ];
            t_end = 300.0, points = 301,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        for t in (0.0, 25.0, 50.0, 100.0, 300.0)
            T = Ta + Q / G * (1 - exp(-t / tau))
            @test isapprox(bg_value(columns, "Body/T", t), T; rtol = 1e-8)
            # The source injects Q: its port flow (into the source) is -Q.
            @test isapprox(bg_value(columns, "Heater/a.f", t), -Q; rtol = 1e-12)
        end
        # Steady state: the conductor carries the whole injected heat flow.
        @test isapprox(bg_value(columns, "Cond/Q", 300.0), Q * (1 - exp(-300.0 / tau)); rtol = 1e-7)
    end
end
