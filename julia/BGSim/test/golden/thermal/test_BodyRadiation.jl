# Golden tests for `stdlib:thermal/BodyRadiation`, `Convection`, `VariableConvection` and
# `PrescribedHeatFlow`, through the real pipeline.
#
# 1. Radiation and convection equilibrium. A body heated by Q = 40 W loses heat by grey-body
#    radiation and by convection to an ambient Ta = 300 K. The equilibrium temperature T*
#    solves
#        Q = epsilon*sigma*A*(T*^4 - Ta^4) + h*A*(T* - Ta),
#    found here by Newton's method; the run settles on it.
# 2. Radiation between two bodies only. Nothing leaves the pair, so the total heat
#    C1*T1 + C2*T2 is conserved and both bodies end at the capacity-weighted mean
#    (C1*T1(0) + C2*T2(0))/(C1 + C2). The exchanged heat flow is
#    epsilon*sigma*A*(T1^4 - T2^4) at every instant.
# 3. VariableConvection with h from a signal equals Convection with the same constant h.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const _SIGMA = 5.670374419e-8

@testset "golden: BodyRadiation" begin
    @testset "radiation and convection equilibrium" begin
        Q, C, Ta = 40.0, 10.0, 300.0
        epsilon, Ar = 0.8, 0.1
        h, Ac = 5.0, 0.1
        f(T) = epsilon * _SIGMA * Ar * (T^4 - Ta^4) + h * Ac * (T - Ta) - Q
        df(T) = 4 * epsilon * _SIGMA * Ar * T^3 + h * Ac
        Tstar = 400.0
        for _ in 1:50
            Tstar -= f(Tstar) / df(Tstar)
        end
        @test abs(f(Tstar)) < 1e-10

        model = bg_model(
            "RadiationConvection",
            [
                bg_node("n1", "Body", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C)),
                    starts = Dict{String,Any}("T" => string(Ta))),
                bg_node("n2", "Rad", bg_ref("stdlib:thermal/BodyRadiation");
                    params = Dict{String,Any}("epsilon" => string(epsilon), "A" => string(Ar))),
                bg_node("n3", "Conv", bg_ref("stdlib:thermal/Convection");
                    params = Dict{String,Any}("h" => string(h), "A" => string(Ac))),
                bg_node("n4", "Ambient", bg_ref("stdlib:thermal/FixedTemperature");
                    params = Dict{String,Any}("T" => string(Ta))),
                bg_node("n5", "Power", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => string(Q))),
                bg_node("n6", "Heater", bg_ref("stdlib:thermal/PrescribedHeatFlow")),
            ],
            [
                bg_conn("c1", "wire", "n1", "a", "n2", "a"),
                bg_conn("c2", "wire", "n2", "b", "n4", "a"),
                bg_conn("c3", "wire", "n1", "a", "n3", "solid"),
                bg_conn("c4", "wire", "n3", "fluid", "n4", "a"),
                bg_conn("c5", "signal", "n5", "y", "n6", "Q"),
                bg_conn("c6", "wire", "n6", "a", "n1", "a"),
            ];
            t_end = 400.0, points = 401,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 1
        T_end = bg_value(columns, "Body/T", 400.0)
        @test isapprox(T_end, Tstar; rtol = 1e-8)
        # At equilibrium the radiated and convected heat flows add up to the input.
        q_rad = bg_value(columns, "Rad/Q", 400.0)
        q_conv = bg_value(columns, "Conv/Q", 400.0)
        @test isapprox(q_rad, epsilon * _SIGMA * Ar * (T_end^4 - Ta^4); rtol = 1e-10)
        @test isapprox(q_rad + q_conv, Q; rtol = 1e-7)
        # Monotone heating from the ambient temperature.
        T = bg_all(columns, "Body/T")
        @test all(diff(T) .>= -1e-9)
    end

    @testset "radiation exchange between two bodies conserves heat" begin
        C1, C2 = 20.0, 60.0
        T1, T2 = 600.0, 300.0
        epsilon, A = 0.9, 0.05
        Tmean = (C1 * T1 + C2 * T2) / (C1 + C2)
        model = bg_model(
            "RadiationExchange",
            [
                bg_node("n1", "Hot", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C1)),
                    starts = Dict{String,Any}("T" => string(T1))),
                bg_node("n2", "Rad", bg_ref("stdlib:thermal/BodyRadiation");
                    params = Dict{String,Any}("epsilon" => string(epsilon), "A" => string(A))),
                bg_node("n3", "Cold", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C2)),
                    starts = Dict{String,Any}("T" => string(T2))),
            ],
            [
                bg_conn("c1", "wire", "n1", "a", "n2", "a"),
                bg_conn("c2", "wire", "n2", "b", "n3", "a"),
            ];
            t_end = 2000.0, points = 201,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test flat.stats.states == 2
        for t in (0.0, 10.0, 100.0, 500.0, 2000.0)
            a = bg_value(columns, "Hot/T", t)
            b = bg_value(columns, "Cold/T", t)
            @test isapprox(C1 * a + C2 * b, C1 * T1 + C2 * T2; rtol = 1e-10)
            @test isapprox(bg_value(columns, "Rad/Q", t), epsilon * _SIGMA * A * (a^4 - b^4);
                rtol = 1e-9, atol = 1e-9)
        end
        @test isapprox(bg_value(columns, "Hot/T", 2000.0), Tmean; rtol = 1e-6)
        @test isapprox(bg_value(columns, "Cold/T", 2000.0), Tmean; rtol = 1e-6)
    end

    @testset "VariableConvection with a constant h equals Convection" begin
        C, Ta, T0 = 50.0, 290.0, 360.0
        h, A = 12.0, 0.2
        tau = C / (h * A)
        model = bg_model(
            "VariableConvection",
            [
                bg_node("n1", "Body", bg_ref("stdlib:thermal/HeatCapacitor");
                    params = Dict{String,Any}("C" => string(C)),
                    starts = Dict{String,Any}("T" => string(T0))),
                bg_node("n2", "Film", bg_ref("stdlib:thermal/VariableConvection");
                    params = Dict{String,Any}("A" => string(A))),
                bg_node("n3", "Air", bg_ref("stdlib:thermal/FixedTemperature");
                    params = Dict{String,Any}("T" => string(Ta))),
                bg_node("n4", "hc", bg_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => string(h))),
            ],
            [
                bg_conn("c1", "wire", "n1", "a", "n2", "solid"),
                bg_conn("c2", "wire", "n2", "fluid", "n3", "a"),
                bg_conn("c3", "signal", "n4", "y", "n2", "h"),
            ];
            t_end = 100.0, points = 101,
        )
        columns, result, _ = bg_run(model)
        @test result.status == "done"
        for t in (0.0, 10.0, 40.0, 100.0)
            T = Ta + (T0 - Ta) * exp(-t / tau)
            @test isapprox(bg_value(columns, "Body/T", t), T; rtol = 1e-8)
            @test isapprox(bg_value(columns, "Film/Q", t), h * A * (T - Ta); rtol = 1e-7)
        end
    end
end
