# Golden test for `stdlib:sources/Triangle`, through the real pipeline.
#
# Model: two Triangle instances, each driving an Integrator: S1 with its kinks on the
# 0.01 s output grid (period 0.2 s from 0.1 s), S2 off the grid (period 0.37 s from 0.023 s).
#
# Reference: y = offset + amplitude * (2f for f < 1/2, else 2(1 - f)) with f the fraction
# of the period since t_start, offset before t_start; the integrals are the exact areas.
#
# Tolerance: 1e-9 on the outputs, 1e-8 on the integrals. No W206, one event per kink.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) || include(joinpath(@__DIR__, "source_helpers.jl"))
using Test
using .BondGraphGolden
using .SourceGolden

@testset "golden: Triangle source" begin
    t_end, points = 1.5, 151
    cases = (
        (amplitude = 2.0, period = 0.2, offset = 0.5, t_start = 0.1),
        (amplitude = 1.0, period = 0.37, offset = 0.0, t_start = 0.023),
    )
    function tri(c, t)
        t < c.t_start && return c.offset
        _, f = period_phase(t, c.t_start, c.period)
        return c.offset + c.amplitude * (f < 0.5 ? 2.0 * f : 2.0 * (1.0 - f))
    end
    params(c) = Dict("amplitude" => string(c.amplitude), "period" => string(c.period),
        "offset" => string(c.offset), "t_start" => string(c.t_start))

    columns, result = run_sources("Triangle", [params(c) for c in cases];
        t_end = t_end, points = points)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    # Two kinks per period: 14 + 8 up to t_end (plus the half-period kinks before t_start,
    # which the second family also crosses), with slack: no chatter.
    @test result.stats.events <= 40

    for (i, c) in enumerate(cases)
        breaks = vcat(edges(c.t_start, c.period, t_end),
            edges(c.t_start + 0.5 * c.period, c.period, t_end))
        ey, ea = source_errors(columns, i, t -> tri(c, t), breaks; t_end = t_end, points = points)
        @test ey < 1e-9
        @test ea < 1e-8
    end
end
