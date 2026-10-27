# Golden test for `stdlib:translation/SpringDamper` (plan section 8, M2 row: Spring-damper),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a `VelocitySource` (v = 0.05 m/s, driven by a Constant) prescribes the relative
# velocity on `SpringDamper.a`; `SpringDamper.b` is wired to a `Fixed` point. In D8's
# Translation convention the across variable is the velocity `f` and the through variable the
# force `e`, so the wire sets `a.f = b.f + v` and `b.f = 0`, hence
#
#   x(t) = v*t,  a.e = k*x + d*v,  b.e = -a.e.
#
# The state `x` is integral (preferred causality), so the run is an index-1 ODE.
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10), plus
# the force balance at both wires and the power balance of the whole model.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: SpringDamper" begin
    k = 2000.0                     # N/m
    d = 20.0                       # N*s/m
    v = 0.05                       # m/s, the imposed relative velocity
    force(t) = k * (v * t) + d * v
    displacement(t) = v * t

    model = bg_model(
        "SpringDamperConstantVelocity",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "0.05")),
            bg_node("n3", "SD1", bg_ref("stdlib:translation/SpringDamper");
                params = Dict{String,Any}("k" => "2000.0", "d" => "20.0")),
            bg_node("n4", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.1, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 1                 # the relative displacement x

    for t in (0.0, 0.01, 0.02, 0.05, 0.08, 0.1)
        # The block: the imposed velocity and the spring-damper law.
        @test isapprox(bg_value(columns, "V1/u", t), 1.0; rtol = 1e-9)  # Constant
        @test isapprox(bg_value(columns, "V1/a.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "SD1/a.f", t), v; rtol = 1e-9)
        @test isapprox(bg_value(columns, "SD1/b.f", t), 0.0; atol = 1e-12)
        @test isapprox(bg_value(columns, "SD1/x", t), displacement(t); rtol = 1e-9,
            atol = 1e-12)
        @test isapprox(bg_value(columns, "SD1/a.e", t), force(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "SD1/b.e", t), -force(t); rtol = 1e-6)
        # The two wires: the flow source absorbs the reaction force, the fixed point
        # carries the same force the spring-damper delivers.
        @test isapprox(bg_value(columns, "V1/a.e", t), -force(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "F1/a.e", t), force(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "F1/a.f", t), 0.0; atol = 1e-12)
        # Power balance: V1/a.P + SD1/a.P + SD1/b.P + F1/a.P = 0 (D15 records every port).
        power = bg_value(columns, "V1/a.P", t) + bg_value(columns, "SD1/a.P", t) +
                bg_value(columns, "SD1/b.P", t) + bg_value(columns, "F1/a.P", t)
        @test abs(power) <= 1e-9
        # The spring-damper receives k*x*v + d*v^2 and the fixed side transmits no power.
        @test isapprox(bg_value(columns, "SD1/a.P", t), force(t) * v; rtol = 1e-6)
        @test isapprox(bg_value(columns, "SD1/b.P", t), 0.0; atol = 1e-9)
    end

    # The whole recorded grid, not only the sample points.
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "SD1/x") .- displacement.(times))) < 1e-10
    @test maximum(abs.(bg_all(columns, "SD1/a.e") .- force.(times))) < 1e-8
end
