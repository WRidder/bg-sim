# Golden test for `stdlib:converters/RackAndPinion` (plan section 8, M2 row: Rack and
# pinion), through the real pipeline.
#
# Model: a `VelocitySource` (v = 1) driven by a Constant 0.6 holds the rack at 0.6 m/s; the
# pinion port `a` drives a `RotationalDamper` (d = 0.5) against a `FixedShaft`. With pinion
# radius r = 0.02 m the block gives
#
#   b.f = r*a.f  ->  a.f = 0.6/0.02 = 30 rad/s,
#   b.e = -a.e/r ->  a.e = -d*a.f = -15 N*m,  b.e = 750 N.
#
# The rack takes 750*0.6 = 450 W in and the pinion delivers 15*30 = 450 W to the damper.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: RackAndPinion" begin
    v = 0.6
    r = 0.02
    d = 0.5
    w = v / r
    torque = d * w
    force = torque / r

    model = bg_model(
        "RackAndPinionDrivesDamper",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v))),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "1.0")),
            bg_node("n3", "R1", bg_ref("stdlib:converters/RackAndPinion");
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
        @test isapprox(bg_value(columns, "R1/b.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "R1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "R1/a.e", t), -torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "R1/b.e", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.e", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), -force; rtol = 1e-9)
        # Power: the rack delivers exactly what the damper dissipates.
        @test isapprox(bg_value(columns, "R1/b.P", t), force * v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "R1/a.P", t), -torque * w; rtol = 1e-9)
        @test abs(bg_value(columns, "R1/a.P", t) + bg_value(columns, "R1/b.P", t)) <= 1e-12
        @test isapprox(bg_value(columns, "R1/b.P", t), bg_value(columns, "D1/a.P", t);
            rtol = 1e-9)
    end
end
