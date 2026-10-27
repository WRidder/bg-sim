# Golden test for `stdlib:discrete/DiscreteTF` (plan section 8, M2 row: Discrete transfer
# function), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Constant 1 drives the transfer function b(z)/a(z) with b = [0.5, 0.25, 0] and
# a = [1, -0.5, 0] on a 1 ms clock, so the recurrence is
#   y[k] = 0.5*u[k] + 0.25*u[k-1] + 0.5*y[k-1].
#
# Reference: that recurrence, evaluated in the test with the same operation order as the
# generated code (accumulate b, subtract a, divide by a[1], then shift both histories), which
# has the closed form y[k] = 1.5 - 0.5^(k-1) for k >= 1. Every coefficient is a binary
# fraction and u is 1, so the sequence is bit-exact and compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: DiscreteTF" begin
    b = [0.5, 0.25, 0.0]
    a = [1.0, -0.5, 0.0]
    u = 1.0

    function reference(b, a, u, n)
        N = length(b)
        uh, yh = zeros(N), zeros(N)
        values = Float64[0.0]
        for _ in 1:n
            acc = b[1] * u
            for k in 2:N
                acc = acc + b[k] * uh[k - 1]
            end
            for k in 2:N
                acc = acc - a[k] * yh[k - 1]
            end
            y = acc / a[1]
            push!(values, y)
            hu, hy = copy(uh), copy(yh)
            for k in 2:N
                hu[k] = uh[k - 1]
                hy[k] = yh[k - 1]
            end
            hu[1], hy[1] = u, y
            uh, yh = hu, hy
        end
        return values
    end

    model = dg_model(
        "DiscreteTFAgainstRecurrence",
        [
            dg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            dg_node("n2", "F1", bg_ref("stdlib:discrete/DiscreteTF");
                params = Dict{String,Any}("b" => "[0.5, 0.25, 0.0]",
                    "a" => "[1.0, -0.5, 0.0]")),
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
    @test dg_values(columns, "F1/y", grid) == expected

    # The closed form of this recurrence and its first values.
    for k in 1:8
        @test expected[k + 1] == 1.5 - 0.5^(k - 1)
    end
    @test expected[2] == 0.5
    @test expected[3] == 1.0
    @test expected[4] == 1.25
    @test expected[9] == 1.5 - 0.5^7

    # The history shift is one sample per tick: uh[1] is the sample taken this tick and
    # uh[2] the one taken the tick before.
    @test bg_value(columns, "F1/uh[1]", 0.001) == 1.0
    @test bg_value(columns, "F1/uh[2]", 0.001) == 0.0
    @test bg_value(columns, "F1/uh[2]", 0.002) == 1.0
    @test bg_value(columns, "F1/yh[1]", 0.001) == 0.5
    @test bg_value(columns, "F1/yh[2]", 0.002) == 0.5
end
