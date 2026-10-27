# Golden test for `stdlib:rotation/SpeedSource` (plan section 8, M2 row: Speed source),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a `Constant` drives the source input `u`; the source fixes `a.f = w*u` (D6 flow
# causality) and a `RotationalDamper` with `d` between `a` and a `FixedShaft` reacts against
# it. With `b.f = 0` the damper torque is `d*w*u`, so
#
#   SpeedSource.a.f = w*u,  Damper.a.e = d*w*u,  SpeedSource.a.e = -d*w*u,
#   P_source = -d*(w*u)^2,  P_damper = +d*(w*u)^2.
#
# Tolerance: rtol 1e-9 against the analytic algebraic values.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: SpeedSource" begin
    w = 2.5          # rad/s per unit input
    d = 0.4          # N*m*s/rad
    u = 1.0
    flow = w * u
    torque = d * flow

    model = bg_model(
        "SpeedSourceDrivesDamper",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(u))),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "D1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => string(d))),
            bg_node("n4", "F1", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0
    for t in (0.0, 0.005, 0.01)
        @test isapprox(bg_value(columns, "W1/u", t), u; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.f", t), flow; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.f", t), flow; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/b.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "D1/a.e", t), torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/b.e", t), -torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.e", t), -torque; rtol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.P", t), -torque * flow; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.P", t), torque * flow; rtol = 1e-9)
        @test abs(bg_value(columns, "W1/a.P", t) + bg_value(columns, "D1/a.P", t) +
                  bg_value(columns, "D1/b.P", t) + bg_value(columns, "F1/a.P", t)) <= 1e-12
    end
end
