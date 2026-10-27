# Golden test for `stdlib:discrete/DiscreteSS` (plan section 8, M2 row: Discrete state space),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Constant 1 drives a two-state discrete state-space model on a 1 ms clock with
#   A = [0.5 0.25; 0 0.5], B = [1.0, 0.5], C = [1, 1], D = 0.25.
#
# Reference: x[k+1] = A*x[k] + B*u, y[k] = C*x[k] + D*u with x[0] = 0, evaluated in the test
# from the same matrices. Every product is a binary fraction of small integers, so the
# sequence is bit-exact and compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: DiscreteSS" begin
    A = [0.5 0.25; 0.0 0.5]
    B = [1.0, 0.5]
    C = [1.0, 1.0]
    D = 0.25
    u = 1.0

    function reference(A, B, C, D, u, n)
        x = zeros(length(B))
        xs, ys = [copy(x)], Float64[]
        for _ in 1:n
            x = A * x + B * u
            push!(xs, copy(x))
            push!(ys, C[1] * x[1] + C[2] * x[2] + D * u)
        end
        return xs, ys
    end

    model = dg_model(
        "DiscreteSSAgainstMatrixRecurrence",
        [
            dg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            dg_node("n2", "S1", bg_ref("stdlib:discrete/DiscreteSS");
                params = Dict{String,Any}("A" => "[0.5 0.25; 0.0 0.5]",
                    "B" => "[1.0, 0.5]", "C" => "[1.0, 1.0]", "D" => "0.25")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0                 # the discrete state is a held value

    xs, ys = reference(A, B, C, D, u, 8)
    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "S1/y", grid) == vcat(0.0, ys)
    @test dg_values(columns, "S1/x[1]", grid) == [state[1] for state in xs]
    @test dg_values(columns, "S1/x[2]", grid) == [state[2] for state in xs]

    # The literal first steps, so the test does not only compare two implementations.
    @test ys[1] == 1.75                          # x[1] = 1, x[2] = 0.5, D*u = 0.25
    @test ys[2] == 2.625
    @test xs[3] == [1.625, 0.75]
    @test ys[8] == C[1] * xs[9][1] + C[2] * xs[9][2] + D * u
end
