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
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: AccelerationSensor" begin
    amplitude = 0.3
    omega = 10.0
    model = bg_model(
        "AccelerationSensorOnSineVelocity",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}(
                    "amplitude" => string(amplitude), "frequency" => string(omega))),
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

    columns, result, flat = bg_run(model)
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
