# Golden test for `stdlib:discrete/IntegerDelay` (J-EX9: the discrete `delay` ring), through
# the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test ramp (1, 2, 3, ... on a 1 ms clock) drives three IntegerDelays on
# the same clock: N = 3, N = 3 with initial 5, and N = 0.
#
# Reference: tick n (t = n ms) samples the ramp value n, and y[n] = u[n - N] once N samples
# have arrived, `initial` before (and the declared start 0 before the first tick); N = 0
# passes the sample through. Whole numbers are exact in Float64, so the sequences compare
# with `==`. A delay that is not a whole number of ticks, or negative, is E104 at the block.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

@testset "golden: IntegerDelay" begin
    model = dg_model(
        "IntegerDelayAgainstExactSequence",
        [
            dg_node("n1", "R1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp(period = 1.0e-3)))),
            dg_node("n2", "D3", bg_ref("stdlib:discrete/IntegerDelay");
                constants = Dict{String,Any}("N" => 3)),
            dg_node("n3", "D3i", bg_ref("stdlib:discrete/IntegerDelay");
                constants = Dict{String,Any}("N" => 3),
                params = Dict{String,Any}("initial" => "5.0")),
            dg_node("n4", "D0", bg_ref("stdlib:discrete/IntegerDelay");
                constants = Dict{String,Any}("N" => 0)),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n1", "y", "n3", "u"),
            bg_conn("c3", "signal", "n1", "y", "n4", "u"),
        ];
        t_end = 0.01, points = 11,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0
    # One ring of three slots per N = 3 instance; N = 0 has none.
    @test Compile.discrete_rings(flat.discrete) == [3, 3]

    grid = dg_grid(0.01; points = 11)            # 1 ms spacing: t = n ms
    n = 0:10
    @test dg_values(columns, "R1/y", grid) == Float64.(n)
    @test dg_values(columns, "D3/y", grid) == Float64[k <= 3 ? 0 : k - 3 for k in n]
    @test dg_values(columns, "D3i/y", grid) ==
          Float64[k == 0 ? 0 : k <= 3 ? 5 : k - 3 for k in n]
    @test dg_values(columns, "D0/y", grid) == Float64.(n)

    # The ring is a run's state: a second run starts empty again.
    columns2, _, _ = bg_run(model)
    @test dg_values(columns2, "D3/y", grid) == dg_values(columns, "D3/y", grid)

    @testset "E104: the delay must be a whole number of ticks" begin
        for (consts, needle) in (
            (Dict{String,Any}("delay_time" => 0.0105, "sample_period" => 0.001),
                "not a whole number of ticks"),
            (Dict{String,Any}("delay_time" => 0.0005, "sample_period" => 0.001), "negative"),
        )
            m = bg_model("BadDelay", [
                    bg_node("n1", "S", bg_ref("stdlib:sources/Sine")),
                    dg_node("n2", "TD", bg_ref("stdlib:continuous/TransportDelay");
                        constants = consts),
                ], [bg_conn("c1", "signal", "n1", "y", "n2", "u")])
            flat_bad = Compile.flatten(IR.parse_model(m))
            d = findfirst(d -> d.code == "E104", flat_bad.diagnostics)
            @test d !== nothing
            d === nothing || (@test occursin(needle, flat_bad.diagnostics[d].message) &&
                                    flat_bad.diagnostics[d].path == "TD")
        end
    end
end
