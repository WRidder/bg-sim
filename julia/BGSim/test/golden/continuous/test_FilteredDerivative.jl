# Golden test for `stdlib:continuous/FilteredDerivative` (plan section 8, M2 row: filtered
# derivative), through the real pipeline.
#
# Model: a Step from 0 to 2 at t = 0.1 s drives the block with Tf = 0.25 s.
#
# Reference: the analytic filtered derivative of a step. With x' = (u - x)/Tf and x(0) = 0,
#   y = (u - x)/Tf = (2/Tf) * exp(-(t - 0.1)/Tf) = 8 * exp(-4*(t - 0.1))   for t >= 0.1,
# and y = 0 before the step.
# Tolerance: rtol 1e-6 at the sampled points (the run uses reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: FilteredDerivative" begin
    Tf = 0.25
    t_step = 0.1
    amp = 2.0
    model = bg_model(
        "FilteredDerivativeOfStep",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => string(t_step),
                    "initial" => "0.0", "final" => string(amp))),
            bg_node("n2", "F1", bg_ref("stdlib:continuous/FilteredDerivative");
                params = Dict{String,Any}("Tf" => string(Tf))),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1

    exact(t) = t < t_step ? 0.0 : (amp / Tf) * exp(-(t - t_step) / Tf)
    for t in (0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "F1/y", t), exact(t); rtol = 1e-6, atol = 1e-9)
    end
    @test bg_value(columns, "F1/y", t_step) > 0.0   # the step's right limit is the impulse
end
