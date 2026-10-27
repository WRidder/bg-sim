# Golden test for `stdlib:discrete/Quantizer` (plan section 8, M2 row: Quantizer), through the
# real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: two discrete test ramps with increments +0.375 (up) and -0.375 (down) drive a
# quantizer with resolution 0.25 on a 1 ms clock. The step is 1.5 resolution units, so every
# second sample is exactly half way between two levels and exercises the tie rule (round half
# away from zero).
#
# Reference: y = resolution * round(u / resolution) with the language's `round`, evaluated in
# the test with the same formula. Every value is a binary fraction, so the comparison is `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Quantizer" begin
    resolution = 0.25
    # The language's round: half away from zero (plan 5.8), never the IEEE tie-to-even.
    quantize(x) = resolution *
                  (x >= 0 ? floor(x / resolution + 0.5) : ceil(x / resolution - 0.5))

    function ramp(increment, n)
        values = Float64[0.0]
        acc = 0.0
        for _ in 1:n
            acc = acc + increment
            push!(values, acc)
        end
        return values
    end

    model = dg_model(
        "QuantizerTiesAwayFromZero",
        [
            dg_node("n1", "U1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(increment = 0.375)))),
            dg_node("n2", "D1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(increment = -0.375)))),
            dg_node("n3", "QU", bg_ref("stdlib:discrete/Quantizer");
                params = Dict{String,Any}("resolution" => "0.25")),
            dg_node("n4", "QD", bg_ref("stdlib:discrete/Quantizer");
                params = Dict{String,Any}("resolution" => "0.25")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n3", "u"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    up, down = ramp(0.375, 8), ramp(-0.375, 8)
    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "QU/y", grid) == quantize.(up)
    @test dg_values(columns, "QD/y", grid) == quantize.(down)

    # The literal sequence: 0, 0.375 -> 0.5 (tie up), 0.75 -> 0.75, 1.125 -> 1.25 (tie up), ...
    @test quantize.(up) == Float64[0, 0.5, 0.75, 1.25, 1.5, 2.0, 2.25, 2.75, 3.0]
    # Negative ties round away from zero, so the sequence is the mirror image.
    @test quantize.(down) == -quantize.(up)
    @test up[3] == 0.75 && quantize(up[3]) == 0.75
    @test up[4] == 1.125 && quantize(up[4]) == 1.25
end
