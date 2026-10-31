# Golden test for `stdlib:motion/Encoder`, through the real pipeline (`parse` -> `flatten`
# -> `lower` -> `simulate`).
#
# Model: a Ramp angle from -2 rad with slope 15 rad/s (two and a half revolutions in a
# second, through zero) drives two encoders on their 1 ms clock: 8 counts per revolution
# (coarse, so the quantization is visible) and 4096. An Integrator on the angle gives the
# model a continuous state.
#
# Reference: at every tick the encoder samples the angle u and outputs
#   counts = floor(u*cpr/(2 pi)), y = counts*2 pi/cpr, index = mod(counts, cpr) == 0,
# held until the next tick; before the first tick (t = 1 ms) the outputs are 0, 0, false.
# The recorded angle at the tick is the sample, so the comparison is exact (`==`). Also:
# y <= u < y + 2 pi/cpr at every tick, the counts step by at most one per tick at
# 8 counts per revolution, and the index fires once per revolution (counts 0, 8 and 16).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Encoder" begin
    nodes = Any[
        bg_node("r", "Angle", bg_ref("stdlib:sources/Ramp");
            params = Dict{String,Any}("initial" => "-2.0", "slope" => "15.0")),
        bg_node("i", "I", bg_ref("stdlib:continuous/Integrator")),
        bg_node("e1", "E8", bg_ref("stdlib:motion/Encoder");
            params = Dict{String,Any}("cpr" => "8")),
        bg_node("e2", "E4096", bg_ref("stdlib:motion/Encoder")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "r", "y", "i", "u"),
        bg_conn("c2", "signal", "r", "y", "e1", "u"),
        bg_conn("c3", "signal", "r", "y", "e2", "u"),
    ]
    columns, result, _ = bg_run(bg_model("Encoders", nodes, conns; t_end = 1.0, points = 1001))
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])

    ticks = collect(range(0.0, 1.0; length = 1001))[2:end]
    for (name, cpr) in (("E8", 8), ("E4096", 4096))
        @testset "$name" begin
            @test bg_value(columns, "$name/counts", 0.0) == 0.0
            @test bg_value(columns, "$name/index", 0.0) == 0.0
            n = Float64[]
            for t in ticks
                u = bg_value(columns, "Angle/y", t)
                c = floor(u * cpr / 6.283185307179586)
                push!(n, c)
                @test bg_value(columns, "$name/counts", t) == c
                y = bg_value(columns, "$name/y", t)
                @test y == c * 6.283185307179586 / cpr
                @test bg_value(columns, "$name/index", t) == (mod(c, cpr) == 0 ? 1.0 : 0.0)
                @test y <= u + 1e-12 && u < y + 2pi / cpr + 1e-12
            end
            @test n[1] == floor((-2.0 + 15.0e-3) * cpr / 2pi)
            @test n[end] == floor(13.0 * cpr / 2pi)
            cpr == 8 && @test maximum(abs.(diff(n))) == 1.0
        end
    end
    # The coarse index: true exactly while the count is 0, 8 or 16.
    idx = [bg_value(columns, "E8/counts", t) for t in ticks if bg_value(columns, "E8/index", t) == 1.0]
    @test sort(unique(idx)) == [0.0, 8.0, 16.0]
end
