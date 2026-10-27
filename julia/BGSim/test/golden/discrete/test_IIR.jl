# Golden test for `stdlib:discrete/IIR` (plan section 8, M2 row: FIR / IIR filter), through
# the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Constant 1 drives the IIR filter with b = [0.5, 0.5, 0] and a = [1, -0.5].
#
# Reference: y[k] = 0.5*u[k] + 0.5*u[k-1] + 0.5*y[k-1], evaluated in the test with the same
# history shift as the generated code; it has the closed form y[k] = 2 - 1.5*0.5^(k-1) for
# k >= 1. Every coefficient is a binary fraction, so the sequence is bit-exact (`==`).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: IIR" begin
    b = [0.5, 0.5, 0.0]
    a = [1.0, -0.5]
    u = 1.0

    function reference(b, a, u, n)
        N, M = length(b), length(a)
        uh, yh = zeros(N), zeros(M)
        values = Float64[0.0]
        for _ in 1:n
            acc = b[1] * u
            for k in 2:N
                acc = acc + b[k] * uh[k - 1]
            end
            for k in 2:M
                acc = acc - a[k] * yh[k - 1]
            end
            y = acc / a[1]
            push!(values, y)
            hu, hy = copy(uh), copy(yh)
            for k in 2:N
                hu[k] = uh[k - 1]
            end
            for k in 2:M
                hy[k] = yh[k - 1]
            end
            hu[1], hy[1] = u, y
            uh, yh = hu, hy
        end
        return values
    end

    model = dg_model(
        "IIRAgainstRecurrence",
        [
            dg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            dg_node("n2", "H1", bg_ref("stdlib:discrete/IIR");
                params = Dict{String,Any}("b" => "[0.5, 0.5, 0.0]", "a" => "[1.0, -0.5]")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    expected = reference(b, a, u, 8)
    @test dg_values(columns, "H1/y", grid) == expected

    for k in 1:8
        @test expected[k + 1] == 2.0 - 1.5 * 0.5^(k - 1)
    end
    @test expected[2] == 0.5
    @test expected[3] == 1.25
    @test expected[4] == 1.625
    @test bg_value(columns, "H1/yh[1]", 0.003) == 1.625
end
