# Golden test for `stdlib:sources/Trapezoid` (Modelica.Blocks.Sources.Trapezoid),
# through the real pipeline.
#
# Model: three Trapezoid instances, each driving an Integrator:
#   * S1: a pulse train (rising = falling = 0, width = half the 0.1 s period): its jumps
#     are output-grid times, and each jump is two coinciding breakpoint families;
#   * S2: ramps 0.02 / 0.03 / 0.01 s in a 0.1 s period, offset and amplitude, from
#     t_start = 0.3 s for n_periods = 5 periods only (low afterwards), on the grid;
#   * S3: off the grid (period 0.37 s from 0.023 s), repeating forever.
#
# Reference: the Modelica definition, the right limit at a jump; the integrals are the
# exact areas. Tolerance: 1e-9 on the outputs, 1e-8 on the integrals. No W206.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
isdefined(@__MODULE__, :SourceGolden) || include(joinpath(@__DIR__, "source_helpers.jl"))
using Test
using .BondGraphGolden
using .SourceGolden

@testset "golden: Trapezoid source" begin
    t_end, points = 1.5, 151
    cases = (
        (amplitude = 1.0, rising = 0.0, width = 0.05, falling = 0.0, period = 0.1,
            n_periods = -1, offset = 0.0, t_start = 0.0),
        (amplitude = 2.0, rising = 0.02, width = 0.03, falling = 0.01, period = 0.1,
            n_periods = 5, offset = -0.5, t_start = 0.3),
        (amplitude = 1.5, rising = 0.05, width = 0.1, falling = 0.07, period = 0.37,
            n_periods = -1, offset = 0.25, t_start = 0.023),
    )
    function trap(c, t)
        t < c.t_start && return c.offset
        n, f = period_phase(t, c.t_start, c.period)
        c.n_periods >= 0 && n >= c.n_periods && return c.offset
        b2, b3 = c.rising, c.rising + c.width
        b4 = b3 + c.falling
        s = snap(f * c.period, (b2, b3, b4))
        s < b2 && return c.offset + c.amplitude * s / c.rising
        s < b3 && return c.offset + c.amplitude
        s < b4 && return c.offset + c.amplitude * (1.0 - (s - b3) / c.falling)
        return c.offset
    end
    params(c) = Dict("amplitude" => string(c.amplitude), "rising" => string(c.rising),
        "width" => string(c.width), "falling" => string(c.falling),
        "period" => string(c.period), "n_periods" => string(c.n_periods),
        "offset" => string(c.offset), "t_start" => string(c.t_start))

    columns, result = run_sources("Trapezoid", [params(c) for c in cases];
        t_end = t_end, points = points)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    # Each family crosses its breakpoint once per period (coinciding families together):
    # about 4 x (15 + 12 + 4) condition crossings; anything near the limit is chatter.
    @test result.stats.events <= 4 * 40

    for (i, c) in enumerate(cases)
        breaks = reduce(vcat, [edges(c.t_start + b, c.period, t_end)
            for b in (0.0, c.rising, c.rising + c.width, c.rising + c.width + c.falling)])
        ey, ea = source_errors(columns, i, t -> trap(c, t), breaks; t_end = t_end, points = points)
        @test ey < 1e-9
        @test ea < 1e-8
    end
    # n_periods = 5: low after the fifth period, which ends at 0.8 s.
    @test all(abs.(bg_all(columns, "S2/y")[columns["time"] .> 0.8 + 1e-9] .+ 0.5) .< 1e-12)
end
