# Golden test for `stdlib:continuous/MathFunction` (plan section 8, M2 row: math function),
# through the real pipeline. The selector `fn` is a structural constant (D11): the lowering
# folds `fn == k` and keeps only the selected function.
#
# Model: u = 0.25 + 0.5t drives two instances, fn = 0 (sin) and fn = 12 (sqrt), and each
# output feeds an Integrator so the run has a state.
#
# Reference: sin(u) and sqrt(u) of that ramp, and their analytic integrals.
# Tolerance: rtol 1e-6 at the sampled points.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: MathFunction" begin
    # `bg_node` has no `constants` keyword in the shared helper, so build those two nodes
    # directly from the same model-document shape.
    function node_with_constants(id, name, ref, fn)
        return Dict{String,Any}(
            "id" => id, "name" => name, "block" => bg_ref(ref),
            "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
            "params" => Dict{String,Any}(), "constants" => Dict{String,Any}("fn" => fn),
            "starts" => Dict{String,Any}(),
        )
    end

    model = bg_model(
        "MathFunctionSinAndSqrt",
        [
            bg_node("n1", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "0.5", "initial" => "0.25")),
            node_with_constants("n2", "F1", "stdlib:continuous/MathFunction", 0),
            node_with_constants("n3", "F2", "stdlib:continuous/MathFunction", 12),
            bg_node("n4", "I1", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n5", "I2", bg_ref("stdlib:continuous/Integrator")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n1", "y", "n3", "u"),
            bg_conn("c3", "signal", "n2", "y", "n4", "u"),
            bg_conn("c4", "signal", "n3", "y", "n5", "u"),
        ];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 2

    for t in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0)
        u = 0.25 + 0.5 * t
        @test isapprox(bg_value(columns, "F1/y", t), sin(u); rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "F2/y", t), sqrt(u); rtol = 1e-6, atol = 1e-9)
    end
    # The two integrators prove the selected function is what the run consumes:
    # int_0^t sin(0.25 + 0.5s) ds and int_0^t sqrt(0.25 + 0.5s) ds.
    @test isapprox(
        bg_value(columns, "I1/y", 2.0),
        2.0 * (cos(0.25) - cos(1.25));
        rtol = 1e-6, atol = 1e-9,
    )
    @test isapprox(
        bg_value(columns, "I2/y", 2.0),
        (2.0 / 3.0) * (1.25^1.5 - 0.25^1.5) / 0.5;
        rtol = 1e-6, atol = 1e-9,
    )
end
