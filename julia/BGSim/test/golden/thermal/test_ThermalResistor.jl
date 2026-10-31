# Golden test for `stdlib:thermal/ThermalResistor`, `ThermalConductor`,
# `TemperatureSensor` and `HeatFlowSensor`: steady-state conduction through a wall.
#
# A hot side at Th = 350 K, a wall of two layers in series (R1 = 2 K/W, then a conductance
# G2 = 1/3 W/K, i.e. R2 = 3 K/W) and a cold side at Tc = 300 K. The mid-wall node carries a
# small heat capacity so the model has a state; at steady state it plays no role:
#
#     Q    = (Th - Tc) / (R1 + R2)            = 10 W
#     Tmid = Th - R1*Q                        = 330 K
#
# The node starts at Tc, so the transient is first order with
#     tau = Cm * R1*R2/(R1 + R2)
# and Tmid(t) = Tss + (Tc - Tss)*exp(-t/tau), with Tss = 330 K.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ThermalResistor" begin
    Th, Tc = 350.0, 300.0
    R1, R2 = 2.0, 3.0
    Cm = 5.0
    Q = (Th - Tc) / (R1 + R2)
    Tss = Th - R1 * Q
    tau = Cm * R1 * R2 / (R1 + R2)

    model = bg_model(
        "WallConduction",
        [
            bg_node("n1", "Hot", bg_ref("stdlib:thermal/FixedTemperature");
                params = Dict{String,Any}("T" => string(Th))),
            bg_node("n2", "Flux", bg_ref("stdlib:thermal/HeatFlowSensor")),
            bg_node("n3", "Layer1", bg_ref("stdlib:thermal/ThermalResistor");
                params = Dict{String,Any}("R" => string(R1))),
            bg_node("n4", "Mid", bg_ref("stdlib:thermal/HeatCapacitor");
                params = Dict{String,Any}("C" => string(Cm)),
                starts = Dict{String,Any}("T" => string(Tc))),
            bg_node("n5", "Layer2", bg_ref("stdlib:thermal/ThermalConductor");
                params = Dict{String,Any}("G" => string(1 / R2))),
            bg_node("n6", "Cold", bg_ref("stdlib:thermal/FixedTemperature");
                params = Dict{String,Any}("T" => string(Tc))),
            bg_node("n7", "Probe", bg_ref("stdlib:thermal/TemperatureSensor")),
        ],
        [
            bg_conn("c1", "wire", "n1", "a", "n2", "a"),
            bg_conn("c2", "wire", "n2", "b", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n4", "a", "n5", "a"),
            bg_conn("c5", "wire", "n5", "b", "n6", "a"),
            bg_conn("c6", "wire", "n7", "a", "n4", "a"),
        ];
        t_end = 300.0, points = 301,
    )
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 1

    for t in (0.0, 1.0, 5.0, 20.0)
        Tmid = Tss + (Tc - Tss) * exp(-t / tau)
        @test isapprox(bg_value(columns, "Probe/y", t), Tmid; rtol = 1e-9)
        # The series sensor reads the heat flow from the hot side into the first layer.
        @test isapprox(bg_value(columns, "Flux/y", t), (Th - Tmid) / R1; rtol = 1e-8)
        @test isapprox(bg_value(columns, "Layer1/dT", t), Th - Tmid; rtol = 1e-8)
        # The temperature probe draws no heat flow.
        @test bg_value(columns, "Probe/a.f", t) == 0.0
    end

    # Steady state (300 s is 50 time constants of tau = 6 s): the textbook series-resistance result.
    @test isapprox(bg_value(columns, "Probe/y", 300.0), Tss; rtol = 1e-10)
    @test isapprox(bg_value(columns, "Flux/y", 300.0), Q; rtol = 1e-8)
    @test isapprox(bg_value(columns, "Layer2/Q", 300.0), Q; rtol = 1e-8)
    @test isapprox(bg_value(columns, "Layer1/Q", 300.0), bg_value(columns, "Layer2/Q", 300.0);
        rtol = 1e-8)
end
