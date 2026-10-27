# Golden test for `stdlib:converters/BallScrew` (plan section 8, M2 row: Ball screw),
# through the real pipeline.
#
# Forward (rotation -> translation): a `SpeedSource` holds the screw at 10 rad/s and the nut
# drives a `Damper` (d = 1000) against `Fixed`. With lead = 0.01 m/rev and eta = 0.9,
#
#   v = lead*w/(2*pi) = 0.0159155 m/s,
#   a.e = d*v*lead/(2*pi*eta) = 0.028146 N*m,
#   b.e = -d*v = -15.9155 N,
#   P_b = -eta*P_a.
#
# Back-driven: a `VelocitySource` holds the nut at 1 mm/s and the screw drives a rotational
# damper (d = 10); then P_b = -P_a/eta, so the nut pays 1/eta.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const TWO_PI = 6.283185307179586

@testset "golden: BallScrew" begin
    lead = 0.01
    eta = 0.9

    # Forward: screw input, nut load.
    w = 10.0
    d = 1000.0
    v = lead * w / TWO_PI
    force = d * v
    torque = force * lead / (TWO_PI * eta)
    forward = bg_model(
        "BallScrewDrivesDamper",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "B1", bg_ref("stdlib:converters/BallScrew");
                params = Dict{String,Any}("lead" => string(lead), "eta" => string(eta))),
            bg_node("n4", "D1", bg_ref("stdlib:translation/Damper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n5", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n4", "b", "n5", "a"),
        ];
        t_end = 0.01, points = 11,
    )
    columns, result, flat = bg_run(forward)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "B1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/b.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.e", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/b.e", t), -force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.e", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.P", t), torque * w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/b.P", t), -force * v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.P", t) + bg_value(columns, "B1/b.P", t),
            (1.0 - eta) * torque * w; rtol = 1e-9)
    end

    # Back-driven: nut input, screw load.
    v2 = 1.0e-3
    d2 = 10.0
    w2 = TWO_PI * v2 / lead
    torque_load = d2 * w2
    nut_force = TWO_PI / lead * torque_load / eta
    back = bg_model(
        "BallScrewBackDriven",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v2))),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "1.0")),
            bg_node("n3", "B1", bg_ref("stdlib:converters/BallScrew");
                params = Dict{String,Any}("lead" => string(lead), "eta" => string(eta))),
            bg_node("n4", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d2))),
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
    columns, result, flat = bg_run(back)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "B1/b.f", t), v2; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.f", t), w2; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.e", t), -torque_load; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/b.e", t), nut_force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.P", t), -torque_load * w2; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/b.P", t), nut_force * v2; rtol = 1e-9)
        @test isapprox(bg_value(columns, "B1/a.P", t) + bg_value(columns, "B1/b.P", t),
            (1.0 / eta - 1.0) * torque_load * w2; rtol = 1e-9)
    end
end
