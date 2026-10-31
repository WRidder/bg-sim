# Golden test for `stdlib:converters/AccelerationSensor` (plan section 8, M2 row:
# Acceleration sensor), through the real pipeline.
#
# Model: a `Sine` (amplitude 0.3 m/s, 10 rad/s) drives a `VelocitySource` (v = 1) on a
# translation node with a 500 N*s/m damper. The sensor draws no force and differentiates
# the node velocity through its own state v:
#
#   velocity(t) = 0.3*sin(10*t),   y(t) = 3*cos(10*t) m/s^2.
#
# The explicit derivative of a port velocity raises the DAE index (W201 is the expected
# warning; there is no error), which is why the test checks the warning-free status only
# through the error filter.
#
# Index reduction removes the sensor's state: v is the prescribed velocity, an exact
# function of t, and y its symbolic derivative. The compiled system has no unknowns although
# the flat model has one state. The Sine's `t >= t_start` condition must then not become a
# condition-only callback (MTK's callback reads the empty state vector and throws in the
# first step, which was an E901 at t = 1e-6). The second case starts the sine at t_start,
# so the acceleration jumps there from 0 to amplitude*omega.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function _acc_model(params...)
    return bg_model(
        "AccelerationSensorOnSineVelocity",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}(params...)),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "1.0")),
            bg_node("n3", "D1", bg_ref("stdlib:translation/Damper");
                params = Dict{String,Any}("d" => "500.0")),
            bg_node("n4", "A1", bg_ref("stdlib:converters/AccelerationSensor")),
            bg_node("n5", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n2", "a", "n4", "a"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
        ];
        t_end = 0.5, points = 51,
    )
end

@testset "golden: AccelerationSensor" begin
    amplitude = 0.3
    omega = 10.0
    @testset "sine from t = 0" begin
        columns, result, flat = bg_run(_acc_model(
            "amplitude" => string(amplitude), "frequency" => string(omega)))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test flat.stats.states == 1                 # the sensor's velocity state
        for t in (0.0, 0.05, 0.1, 0.2, 0.3, 0.5)
            @test isapprox(bg_value(columns, "A1/a.f", t), amplitude * sin(omega * t);
                rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "A1/v", t), amplitude * sin(omega * t);
                rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "A1/y", t), amplitude * omega * cos(omega * t);
                rtol = 1e-6, atol = 1e-9)
            @test isapprox(bg_value(columns, "A1/a.e", t), 0.0; atol = 1e-12)
            @test isapprox(bg_value(columns, "A1/a.P", t), 0.0; atol = 1e-12)
        end
    end

    @testset "sine from t_start: the state-free compiled model runs" begin
        t0 = 0.123
        velocity(t) = t < t0 ? 0.0 : amplitude * sin(omega * (t - t0))
        acceleration(t) = t < t0 ? 0.0 : amplitude * omega * cos(omega * (t - t0))
        columns, result, flat = bg_run(_acc_model("amplitude" => string(amplitude),
            "frequency" => string(omega), "t_start" => string(t0)))
        @test result.status == "done"
        @test flat.stats.states == 1
        # No state is left after index reduction, so the kink callback was dropped.
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.5)
        @test isempty(BGSim.ModelingToolkit.unknowns(lowered.model.system))
        @test !haskey(lowered.problem.kwargs, :callback)
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        @test !any(d -> d.code == "E901", result.diagnostics)
        for t in (0.0, 0.05, 0.1, 0.12, 0.13, 0.2, 0.3, 0.5)
            @test isapprox(bg_value(columns, "A1/v", t), velocity(t); atol = 1e-12)
            @test isapprox(bg_value(columns, "A1/y", t), acceleration(t); atol = 1e-9)
        end
    end
end
