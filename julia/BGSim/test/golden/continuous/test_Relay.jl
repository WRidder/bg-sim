# Golden test for `stdlib:continuous/Relay` (plan section 8, M2 row: relay with
# hysteresis), through the real pipeline. The relay is a held state written by two `@events`:
# turn on when the input rises above `hi`, turn off when it falls below `lo`.
#
# Model: u = 2*sin(2*pi*t) (a Sine with frequency 2*pi rad/s) drives the relay with
# hi = 0.5, lo = -0.5, on_value = 1 and off_value = 0. The switching instants are
#   t1 = asin(0.25)/(2*pi)      (rising past 0.5),
#   t2 = (pi + asin(0.25))/(2*pi) (falling past -0.5),
#   t3 = (2*pi - asin(0.25))/(2*pi) (rising past 0.5 again).
#
# Reference: those analytic instants, and the constant relay levels between them.
# Tolerance: the levels exactly (atol 1e-9), the switch instants within 1e-6 s.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Relay" begin
    w = 2.0 * pi
    t1 = asin(0.25) / w
    t2 = (pi + asin(0.25)) / w
    t3 = (2.0 * pi - asin(0.25)) / w

    model = bg_model(
        "RelayWithHysteresis",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "2.0",
                    "frequency" => string(w), "phase" => "0.0", "offset" => "0.0")),
            bg_node("n2", "R1", bg_ref("stdlib:continuous/Relay");
                params = Dict{String,Any}("hi" => "0.5", "lo" => "-0.5",
                    "on_value" => "1.0", "off_value" => "0.0", "leak" => "0.0")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 1.2, points = 121,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test !any(d -> d.code == "W206", result.diagnostics)
    @test flat.stats.states == 1

    # The level between two switching instants, sampled on the output grid.
    for (t, level) in ((0.01, 0.0), (0.3, 1.0), (0.7, 0.0), (1.1, 1.0))
        @test isapprox(bg_value(columns, "R1/y", t), level; atol = 1e-9)
    end

    # The solver lands on the switching instants (the event pairs are at the same t).
    times = columns["time"]
    for ts in (t1, t2, t3)
        @test any(tt -> abs(tt - ts) < 1e-6, times)
    end
end
