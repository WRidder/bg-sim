# Golden test for `stdlib:continuous/Saturation` (plan section 8, M2 row: saturation),
# through the real pipeline.
#
# Model: a Ramp from -3 with slope 2 through a saturation at [-1, 1].
#
# Reference: y = clamp(-3 + 2t, -1, 1), which is -1 until t = 1, the ramp in between and
# +1 from t = 2. The block is algebraic, so the run has no states.
# Tolerance: rtol 1e-6 / atol 1e-9.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Saturation" begin
    model = bg_model(
        "SaturationOfRamp",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "2.0", "initial" => "-3.0")),
            bg_node("n2", "S1", bg_ref("stdlib:continuous/Saturation");
                params = Dict{String,Any}("lower" => "-1.0", "upper" => "1.0")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 2.5, points = 251,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    for t in (0.0, 0.5, 0.9, 1.0, 1.25, 1.5, 2.0, 2.5)
        @test isapprox(bg_value(columns, "S1/y", t), clamp(-3.0 + 2.0 * t, -1.0, 1.0);
            rtol = 1e-6, atol = 1e-9)
    end
    # Before the lower knee and after the upper one the output is exactly the limit.
    @test all(abs.(bg_all(columns, "S1/y")[columns["time"] .< 0.9] .+ 1.0) .< 1e-9)
    @test all(abs.(bg_all(columns, "S1/y")[columns["time"] .> 2.1] .- 1.0) .< 1e-9)
end
