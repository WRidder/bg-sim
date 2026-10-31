# Golden test for `stdlib:motion/ADC` and `stdlib:motion/DAC`, through the real pipeline
# (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Sine of amplitude 1.5 (7 rad/s) drives a 3-bit ADC over -1..1 (lsb 2/7, so the
# input clips over part of each period) and a 4-bit value-mode DAC over -2..2; the ADC code
# drives a 3-bit code-mode DAC over -1..1 (the round trip). An Integrator on the sine gives
# the model a continuous state. Every converter runs on its 1 ms clock.
#
# Reference: at every tick, with u the recorded sample,
#   ADC: code = clamp(round((u + 1)/lsb), 0, 7), y = -1 + code*lsb, lsb = 2/7;
#   DAC (value): y = -2 + clamp(round((u + 2)/lsb4), 0, 15)*lsb4, lsb4 = 4/15;
#   DAC (code): y = -1 + clamp(round(code), 0, 7)*lsb, the ADC level itself.
# `round` is half away from zero, as in the language. All values are compared with `==`.
# Also: the ADC output clips at both ends of the range, and its error is at most lsb/2
# inside the range.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: ADC and DAC" begin
    nodes = Any[
        bg_node("s", "U", bg_ref("stdlib:sources/Sine");
            params = Dict{String,Any}("amplitude" => "1.5", "frequency" => "7.0")),
        bg_node("i", "I", bg_ref("stdlib:continuous/Integrator")),
        bg_node("a", "ADC1", bg_ref("stdlib:motion/ADC");
            params = Dict{String,Any}("bits" => "3", "u_min" => "-1.0", "u_max" => "1.0")),
        bg_node("dv", "DACV", bg_ref("stdlib:motion/DAC");
            params = Dict{String,Any}("bits" => "4", "y_min" => "-2.0", "y_max" => "2.0")),
        bg_node("dc", "DACC", bg_ref("stdlib:motion/DAC");
            params = Dict{String,Any}("bits" => "3", "y_min" => "-1.0", "y_max" => "1.0",
                "input" => "1")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "s", "y", "i", "u"),
        bg_conn("c2", "signal", "s", "y", "a", "u"),
        bg_conn("c3", "signal", "s", "y", "dv", "u"),
        bg_conn("c4", "signal", "a", "code", "dc", "u"),
    ]
    columns, result, _ = bg_run(bg_model("Converters", nodes, conns; t_end = 1.0, points = 1001))
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])

    rnd(x) = x >= 0 ? floor(x + 0.5) : ceil(x - 0.5)
    lsb = 2.0 / (2.0^3 - 1.0)
    lsb4 = 4.0 / (2.0^4 - 1.0)
    ticks = collect(range(0.0, 1.0; length = 1001))[2:end]
    codes = Float64[]
    for t in ticks
        u = bg_value(columns, "U/y", t)
        code = min(max(rnd((u + 1.0) / lsb), 0.0), 7.0)
        push!(codes, code)
        @test bg_value(columns, "ADC1/code", t) == code
        @test bg_value(columns, "ADC1/y", t) == -1.0 + code * lsb
        @test bg_value(columns, "DACV/y", t) == -2.0 + clamp(rnd((u + 2.0) / lsb4), 0.0, 15.0) * lsb4
        @test bg_value(columns, "DACC/y", t) == bg_value(columns, "ADC1/y", t)
        abs(u) <= 1.0 && @test abs(bg_value(columns, "ADC1/y", t) - u) <= lsb / 2 + 1e-12
    end
    # Before the first tick everything is 0; the input clips at both ends.
    @test bg_value(columns, "ADC1/code", 0.0) == 0.0
    @test bg_value(columns, "DACV/y", 0.0) == 0.0
    @test 0.0 in codes && 7.0 in codes
    @test sort(unique(codes)) == collect(0.0:7.0)
    @test maximum(bg_value(columns, "ADC1/y", t) for t in ticks) ≈ 1.0 atol = 1e-12
    @test minimum(bg_value(columns, "ADC1/y", t) for t in ticks) == -1.0
end
