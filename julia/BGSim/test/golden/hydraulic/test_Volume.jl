# Golden test for `stdlib:hydraulic/Volume` (plan section 8, M2 row: Volume), through the
# real pipeline.
#
# Hydraulic convention (D8): across = `e` (pressure), through = `f` (volume flow). A volume
# is the hydraulic C element: `ddt(p) = beta*f/V`, `a.e = p`. Model: a `FlowSource`
# (Q = -1e-6 m^3/s, so +1e-6 enters the volume) charges the volume from zero pressure; its
# return port goes to a `Tank`. The pressure is then exactly linear in time:
#
#   p(t) = p0 + beta*Q_vol*t/V,  Q_vol = 1e-6 m^3/s,  p0 = 0,
#
# (a wired pressure node is an MTK alias, so the block's own `p` start is not the compiled
# state's start; the zero start is exact and still exercises the C element).
# The stored hydraulic energy also follows the analytic charging work:
#   int_0^t p(τ) Q_vol dτ = V/(2*beta) * (p(t)^2 - p0^2).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Volume" begin
    Q = -1.0e-6
    Q_vol = -Q
    V = 1.0e-4
    beta = 1.4e9
    p0 = 0.0
    rate = beta * Q_vol / V

    model = bg_model(
        "VolumeChargedByFlowSource",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "F1", bg_ref("stdlib:hydraulic/FlowSource");
                params = Dict{String,Any}("Q" => string(Q))),
            bg_node("n3", "V1", bg_ref("stdlib:hydraulic/Volume");
                params = Dict{String,Any}("V" => string(V), "beta" => string(beta))),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n2", "b", "n4", "a"),
        ];
        t_end = 1.0e-3, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 1                 # the pressure
    for t in (0.0, 1.0e-4, 5.0e-4, 1.0e-3)
        p = p0 + rate * t
        @test isapprox(bg_value(columns, "V1/a.f", t), Q_vol; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/p", t), p; rtol = 1e-9, atol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), p; rtol = 1e-9, atol = 1e-9)
        # Charging work equals the stored compressibility energy.
        work = Q_vol * (p0 * t + 0.5 * rate * t^2)
        stored = V / (2.0 * beta) * (p^2 - p0^2)
        @test isapprox(work, stored; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.P", t), p * Q_vol; rtol = 1e-9, atol = 1e-9)
    end
end
