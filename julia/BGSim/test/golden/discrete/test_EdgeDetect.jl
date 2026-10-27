# Golden test for `stdlib:discrete/EdgeDetect` (plan section 8, M2 row: Edge detect), through
# the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test toggle (true on odd ticks, false on even ones) drives three edge
# detectors on the same 1 ms clock: rising, falling and both.
#
# Reference: with the input sequence 0 1 0 1 0 1 0 1 0 the outputs are
#   rising:  0 1 0 1 0 1 0 1 0        falling: 0 0 1 0 1 0 1 0 1
#   both:    0 1 1 1 1 1 1 1 1
# A Bool is recorded as 1 or 0, so the sequences are compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: EdgeDetect" begin
    model = dg_model(
        "EdgeDetectModes",
        [
            dg_node("n1", "T1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_toggle()))),
            dg_node("n2", "E0", bg_ref("stdlib:discrete/EdgeDetect");
                params = Dict{String,Any}("mode" => "0")),
            dg_node("n3", "E1", bg_ref("stdlib:discrete/EdgeDetect");
                params = Dict{String,Any}("mode" => "1")),
            dg_node("n4", "E2", bg_ref("stdlib:discrete/EdgeDetect");
                params = Dict{String,Any}("mode" => "2")),
        ],
        [
            bg_conn("c1", "signal", "n1", "q", "n2", "u"),
            bg_conn("c2", "signal", "n1", "q", "n3", "u"),
            bg_conn("c3", "signal", "n1", "q", "n4", "u"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "T1/q", grid) == Float64[0, 1, 0, 1, 0, 1, 0, 1, 0]
    @test dg_values(columns, "E0/y", grid) == Float64[0, 1, 0, 1, 0, 1, 0, 1, 0]
    @test dg_values(columns, "E1/y", grid) == Float64[0, 0, 1, 0, 1, 0, 1, 0, 1]
    @test dg_values(columns, "E2/y", grid) == Float64[0, 1, 1, 1, 1, 1, 1, 1, 1]

    # Rising and falling never overlap, and the both mode is their union.
    @test dg_values(columns, "E2/y", grid) ==
          dg_values(columns, "E0/y", grid) .+ dg_values(columns, "E1/y", grid)
    # `up` holds the sample this tick took; at the next tick that is the previous sample the
    # edge is measured against.
    @test bg_value(columns, "E0/up", 0.001) == 1.0
    @test bg_value(columns, "E0/up", 0.002) == 0.0
end
