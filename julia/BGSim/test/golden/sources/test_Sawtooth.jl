# Golden test for `stdlib:sources/Sawtooth`, through the real pipeline (`parse` ->
# `flatten` -> `lower` -> `simulate`).
#
# Model: two Sawtooth instances, each driving an Integrator:
#   * S1: period 0.1 s from t_start = 0.3 s, so **every edge is an output-grid time** (the
#     0.01 s grid): the case that floods a floor- or trigonometry-based edge with events;
#   * S2: period 0.37 s from t_start = 0.023 s, edges off the grid.
#
# Reference: y = offset + amplitude * frac((t - t_start)/period) from t_start on, else
# offset, taken as the right limit at an edge; the integrals are the exact areas.
#
# Tolerance: 1e-9 on the outputs at the grid points, 1e-8 on the integrals at every
# recorded row (the run uses reltol 1e-10, abstol 1e-12). No W206 and one event per edge.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) || include(joinpath(@__DIR__, "source_helpers.jl"))
using Test
using .BondGraphGolden
using .SourceGolden

@testset "golden: Sawtooth source" begin
    t_end, points = 1.55, 156  # no edge at t_end itself: the run ends on its left limit
    cases = (
        (amplitude = 2.0, period = 0.1, offset = -1.0, t_start = 0.3),
        (amplitude = 1.0, period = 0.37, offset = 0.0, t_start = 0.023),
    )
    function saw(c, t)
        t < c.t_start - 1e-12 && return c.offset
        _, f = period_phase(t, c.t_start, c.period)
        return c.offset + c.amplitude * f
    end
    params(c) = Dict("amplitude" => string(c.amplitude), "period" => string(c.period),
        "offset" => string(c.offset), "t_start" => string(c.t_start))

    columns, result = run_sources("Sawtooth", [params(c) for c in cases];
        t_end = t_end, points = points)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    # One event per edge (13 + 5 up to t_end), with a little slack: no chatter.
    @test result.stats.events <= 24

    for (i, c) in enumerate(cases)
        breaks = vcat([c.t_start], edges(c.t_start, c.period, t_end))
        ey, ea = source_errors(columns, i, t -> saw(c, t), breaks; t_end = t_end, points = points)
        @test ey < 1e-9
        @test ea < 1e-8
    end
end
