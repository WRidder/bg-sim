# Golden test for `stdlib:discrete/FIR` (plan section 8, M2 row: FIR / IIR filter), through
# the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test ramp (1, 2, 3, ... on a 1 ms clock) drives the FIR filter with the
# default b = [0.25, 0.5, 0.25].
#
# Reference: y[k] = 0.25*u[k] + 0.5*u[k-1] + 0.25*u[k-2], evaluated in the test with the same
# history shift as the generated code. The coefficients are binary fractions and the samples
# are whole numbers, so the sequence is bit-exact and compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: FIR" begin
    b = [0.25, 0.5, 0.25]

    function reference(b, samples)
        N = length(b)
        uh = zeros(N)
        values = Float64[0.0]
        for u in samples
            acc = b[1] * u
            for k in 2:N
                acc = acc + b[k] * uh[k - 1]
            end
            push!(values, acc)
            hu = copy(uh)
            for k in 2:N
                hu[k] = uh[k - 1]
            end
            hu[1] = u
            uh = hu
        end
        return values
    end

    samples = Float64.(1:8)
    model = dg_model(
        "FIRAgainstConvolution",
        [
            dg_node("n1", "R1", Dict{String,Any}("inline" =>
                Dict{String,Any}("source" => dg_ramp()))),
            dg_node("n2", "H1", bg_ref("stdlib:discrete/FIR")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    expected = reference(b, samples)
    @test dg_values(columns, "H1/y", grid) == expected

    # y[k] = k - 1 for k >= 2: the symmetric filter of a ramp is the ramp, delayed by one.
    @test expected[1] == 0.0
    @test expected[2] == 0.25
    @test expected[3] == 1.0
    @test expected[9] == 7.0
    # The history buffer holds the two previous samples, newest first.
    @test bg_value(columns, "H1/uh[1]", 0.003) == 3.0
    @test bg_value(columns, "H1/uh[2]", 0.003) == 2.0
end
