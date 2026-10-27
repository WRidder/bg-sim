# Golden test for `stdlib:converters/Wheel` (plan section 8, M2 row: Wheel), through the
# real pipeline.
#
# Model: a `VelocitySource` (v = 1) driven by a Constant 3 holds the contact patch at
# 3 m/s; the wheel's rotation port drives a `RotationalDamper` (d = 2) against `FixedShaft`.
# With radius r = 0.3 m:
#
#   w = v/r = 10 rad/s,  a.e = -d*w = -20 N*m,  b.e = -a.e/r = 66.667 N,
#   P_b = 200 W in, P_a = -200 W out: the damper dissipates exactly the wheel's input.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Wheel" begin
    v = 3.0
    r = 0.3
    d = 2.0
    w = v / r
    torque = d * w
    force = torque / r

    model = bg_model(
        "WheelRollsAgainstDamper",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v))),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "1.0")),
            bg_node("n3", "W1", bg_ref("stdlib:converters/Wheel");
                params = Dict{String,Any}("r" => string(r))),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "b"),
            bg_conn("c3", "wire", "n3", "a", "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "W1/b.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.e", t), -torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/b.e", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.e", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), -force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/b.P", t), force * v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.P", t), -torque * w; rtol = 1e-9)
        @test abs(bg_value(columns, "W1/a.P", t) + bg_value(columns, "W1/b.P", t)) <= 1e-12
        @test isapprox(bg_value(columns, "W1/b.P", t), bg_value(columns, "D1/a.P", t);
            rtol = 1e-9)
    end
end
