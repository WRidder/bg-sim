# Golden test for `stdlib:sources/RepeatingTable`, through the real pipeline.
#
# Model: four RepeatingTable instances on one 8-value table, each driving an Integrator:
# linear and hold with the samples on the 0.01 s output grid (sample_time 0.03 s from
# 0.3 s), and linear and hold off the grid (sample_time 0.037 s from 0.023 s).
#
# Reference: the table repeated with period 8*sample_time; hold keeps value i over sample
# i, linear interpolates from value i to i + 1 and over the last sample from value 8 back to
# value 1; values[1] before t_start. The right limit at a jump; the integrals are the exact
# areas. Tolerance: 1e-9 on the outputs, 1e-8 on the integrals. No W206.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) || include(joinpath(@__DIR__, "source_helpers.jl"))
using Test
using .BondGraphGolden
using .SourceGolden

@testset "golden: RepeatingTable source" begin
    t_end, points = 1.5, 151
    vals = [0.0, 1.0, -0.5, 2.0, 0.25, -1.0, 1.5, 0.75]
    n = length(vals)
    cases = (
        (sample_time = 0.03, t_start = 0.3, method = 1),
        (sample_time = 0.03, t_start = 0.3, method = 0),
        (sample_time = 0.037, t_start = 0.023, method = 1),
        (sample_time = 0.037, t_start = 0.023, method = 0),
    )
    function table(c, t)
        t < c.t_start && return vals[1]
        _, f = period_phase(t, c.t_start, n * c.sample_time)
        s = f * n
        j = round(s)
        abs(s - j) < 1e-9 && (s = j)               # on a sample: the right limit
        i = min(floor(Int, s), n - 1)              # 0-based sample index
        c.method == 0 && return vals[i + 1]
        nxt = i + 2 > n ? vals[1] : vals[i + 2]
        return vals[i + 1] + (nxt - vals[i + 1]) * (s - i)
    end
    params(c) = Dict("sample_time" => string(c.sample_time), "t_start" => string(c.t_start),
        "method" => string(c.method), "values" => "[" * join(vals, ", ") * "]")

    columns, result = run_sources("RepeatingTable", [params(c) for c in cases];
        t_end = t_end, points = points)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)

    for (i, c) in enumerate(cases)
        breaks = vcat([c.t_start], reduce(vcat, [edges(c.t_start + k * c.sample_time,
            n * c.sample_time, t_end) for k in 0:n - 1]))
        ey, ea = source_errors(columns, i, t -> table(c, t), breaks; t_end = t_end, points = points)
        @test ey < 1e-9
        @test ea < 1e-8
    end
end
