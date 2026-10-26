# Golden test for `stdlib:continuous/DeadZone` (plan section 8, M2 row: dead zone), through
# the real pipeline.
#
# Model: a Ramp from -3 with slope 2 through a dead zone at [-1, 1].
#
# Reference: y = 0 inside [-1, 1], u - upper above and u - lower below:
#   y = -3+2t+1 for u < -1 (t < 1), 0 for 1 <= t <= 2, and -3+2t-1 for t > 2.
# The block is algebraic, so the run has no states.
# Tolerance: rtol 1e-6 / atol 1e-9.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: DeadZone" begin
    model = bg_model(
        "DeadZoneOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "2.0", "initial" => "-3.0")),
            bg_node("n2", "D1", bg_ref("stdlib:continuous/DeadZone");
                params = Dict{String,Any}("lower" => "-1.0", "upper" => "1.0")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 2.5, points = 251,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    function exact(t)
        u = -3.0 + 2.0 * t
        return u > 1.0 ? u - 1.0 : (u < -1.0 ? u + 1.0 : 0.0)
    end
    for t in (0.0, 0.5, 1.0, 1.25, 1.75, 2.0, 2.25, 2.5)
        @test isapprox(bg_value(columns, "D1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    @test all(abs.(bg_all(columns, "D1/y")[1.05 .< columns["time"] .< 1.95]) .< 1e-9)
end
