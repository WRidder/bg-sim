# Golden test for `stdlib:rotation/ElasticShaft` (plan section 8, M2 row: Elastic shaft),
# through the real pipeline.
#
# Model: a `SpeedSource` with `w` drives port `a` at constant speed; `b` is a
# `FixedShaft`. With `w_rel = a.f - b.f = w` constant,
#
#   phi(t) = phi0 + w*t,   a.e = k*phi + d*w,   b.e = -a.e,
#
# and the source absorbs the reaction. The shaft is a C element, so the run has one state.
# Tolerance: rtol 1e-6 against the analytic values (reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ElasticShaft" begin
    w = 3.0          # rad/s
    k = 200.0        # N*m/rad
    d = 0.5          # N*m*s/rad
    model = bg_model(
        "ElasticShaftDrivenAtConstantSpeed",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "W1", bg_ref("stdlib:rotation/SpeedSource");
                params = Dict{String,Any}("w" => string(w))),
            bg_node("n3", "S1", bg_ref("stdlib:rotation/ElasticShaft");
                params = Dict{String,Any}("k" => string(k), "d" => string(d))),
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
    @test flat.stats.states == 1                 # the twist angle

    for t in (0.0, 1.0e-3, 5.0e-3, 0.01)
        phi = w * t
        torque = k * phi + d * w
        @test isapprox(bg_value(columns, "S1/a.f", t), w; rtol = 1e-9)
        @test isapprox(bg_value(columns, "S1/b.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "S1/phi", t), phi; rtol = 1e-6, atol = 1e-12)
        @test isapprox(bg_value(columns, "S1/a.e", t), torque; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "S1/b.e", t), -torque; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "W1/a.e", t), -torque; rtol = 1e-6, atol = 1e-9)
        # The source delivers the shaft power; the fixed side carries none of it.
        @test isapprox(bg_value(columns, "S1/a.P", t), torque * w; rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "S1/b.P", t), 0.0; atol = 1e-12)
    end
end
