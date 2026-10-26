# Golden test for `stdlib:continuous/StateSpace` (plan section 8, M2 row: state space),
# through the real pipeline.
#
# Model: the classical second-order system
#   A = [0 1; -2 -3],  B = [0, 1],  C = [1, 0],  D = 0,
# started at x = [1, 0] with a zero input. The eigenvalues are -1 and -2, so
#   y(t) = 2*exp(-t) - exp(-2t).
#
# Reference: that analytic free response. Tolerance: rtol 1e-6 at the sampled points.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: StateSpace" begin
    model = bg_model(
        "StateSpaceFreeResponse",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "0.0")),
            bg_node("n2", "S1", bg_ref("stdlib:continuous/StateSpace");
                params = Dict{String,Any}(
                    "A" => "[0.0 1.0; -2.0 -3.0]",
                    "B" => "[0.0, 1.0]",
                    "C" => "[1.0, 0.0]",
                    "D" => "0.0",
                ),
                starts = Dict{String,Any}("x" => "[1.0, 0.0]")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 4.0, points = 81,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 2

    exact(t) = 2.0 * exp(-t) - exp(-2.0 * t)
    for t in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
        @test isapprox(bg_value(columns, "S1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    # The second state is recorded too, and it is the derivative of the response.
    @test isapprox(bg_value(columns, "S1/x[2]", 1.0), -2.0 * exp(-1.0) + 2.0 * exp(-2.0);
        rtol = 1e-6, atol = 1e-9)
end
