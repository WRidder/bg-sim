# Golden test for `stdlib:hydraulic/FlowSource` (plan section 8, M2 row: Flow source),
# through the real pipeline.
#
# Hydraulic convention (D8): across = `e` (pressure), through = `f` (volume flow). The
# two-terminal source drives `Q*u` into `a` and returns it through `b`. Model: `a` charges a
# `Volume` (V, bulk modulus beta) and `b` returns to a `Tank`. With
# the source parameter Q = -1e-6 m^3/s (so the flow into the volume is +1e-6 m^3/s) and
# the volume starting at zero pressure (the wired pressure node is an MTK alias, so the
# start value of the block's `p` does not reach the compiled state),
#
#   p(t) = beta*Q_vol*t/V,
#
# and every source/volume flow is constant. Tolerance: rtol 1e-9 for the integrated
# pressure (reltol 1e-10) and the algebraic flows.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: FlowSource" begin
    Q = -1.0e-6          # m^3/s; the volume receives +1e-6
    V = 1.0e-4           # m^3
    beta = 1.4e9         # Pa
    p0 = 0.0             # Pa (the volume starts empty; see the alias note)
    p_tank = 1.0e5
    rate = beta * (-Q) / V

    model = bg_model(
        "FlowSourceChargesVolume",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "F1", bg_ref("stdlib:hydraulic/FlowSource");
                params = Dict{String,Any}("Q" => string(Q))),
            bg_node("n3", "V1", bg_ref("stdlib:hydraulic/Volume");
                params = Dict{String,Any}("V" => string(V), "beta" => string(beta))),
            bg_node("n4", "T1", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_tank))),
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
    @test flat.stats.states == 1                 # the volume pressure
    for t in (0.0, 1.0e-4, 5.0e-4, 1.0e-3)
        p = rate * t
        @test isapprox(bg_value(columns, "F1/u", t), 1.0; rtol = 1e-12)
        @test isapprox(bg_value(columns, "F1/a.f", t), Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "F1/b.f", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.f", t), -Q; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/p", t), p; rtol = 1e-9, atol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), p; rtol = 1e-9, atol = 1e-9)
        @test isapprox(bg_value(columns, "T1/a.e", t), p_tank; rtol = 1e-9)
        # The hydraulic power into the volume is p * Q_vol.
        @test isapprox(bg_value(columns, "V1/a.P", t), p * (-Q); rtol = 1e-9, atol = 1e-9)
    end
end
