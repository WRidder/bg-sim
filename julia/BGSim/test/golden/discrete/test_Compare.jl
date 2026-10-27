# Golden test for `stdlib:discrete/Compare` (plan section 8, M2 row: Compare), through the real
# pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a discrete test ramp (u1 = 1, 2, 3, ... on a 1 ms clock) is compared with a Constant
# 2.5 through all six operators; two further instances compare it with a Constant 2.0, which
# the ramp equals exactly at tick 2.
#
# Reference: the six operators evaluated on the exact samples, with a Bool recorded as 1 or 0.
# All comparisons are exact, so the sequences are compared with `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Compare" begin
    ops = ["==", "!=", "<", "<=", ">", ">="]
    reference(op, u1, u2) = op == "==" ? Float64(u1 == u2) :
                            op == "!=" ? Float64(u1 != u2) :
                            op == "<" ? Float64(u1 < u2) :
                            op == "<=" ? Float64(u1 <= u2) :
                            op == ">" ? Float64(u1 > u2) : Float64(u1 >= u2)

    nodes = Any[
        dg_node("n1", "R1", Dict{String,Any}("inline" =>
            Dict{String,Any}("source" => dg_ramp()))),
        dg_node("n2", "C1", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "2.5")),
        dg_node("n3", "C2", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => "2.0")),
    ]
    connections = Any[]
    for (i, op) in enumerate(ops)
        push!(nodes, dg_node("k$i", "Q$i", bg_ref("stdlib:discrete/Compare");
            params = Dict{String,Any}("op" => string(i - 1))))
        push!(connections, bg_conn("c$i", "signal", "n1", "y", "k$i", "u1"))
        push!(connections, bg_conn("d$i", "signal", "n2", "y", "k$i", "u2"))
    end
    # `==` and `!=` against exactly 2.0: only tick 2 is equal.
    for (ref, i, op) in (("E", 1, "=="), ("N", 2, "!="))
        push!(nodes, dg_node("m$ref", ref, bg_ref("stdlib:discrete/Compare");
            params = Dict{String,Any}("op" => string(i - 1))))
        push!(connections, bg_conn("e$ref", "signal", "n1", "y", "m$ref", "u1"))
        push!(connections, bg_conn("f$ref", "signal", "n3", "y", "m$ref", "u2"))
    end

    model = dg_model("CompareAllOperators", nodes, connections; t_end = 0.008, points = 9)
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    grid = dg_grid(0.008; points = 9)
    # Before the first tick the output is its start value (false); the comparison at tick k
    # sees u1 = k, because the ramp counts up on the tick.
    for (i, op) in enumerate(ops)
        @test dg_values(columns, "Q$i/y", grid) ==
              vcat(0.0, [reference(op, u, 2.5) for u in 1:8])
    end
    @test dg_values(columns, "E/y", grid) == Float64[0, 0, 1, 0, 0, 0, 0, 0, 0]
    @test dg_values(columns, "N/y", grid) == Float64[0, 1, 0, 1, 1, 1, 1, 1, 1]

    # Literal rows: 2 < 2.5 is true, 3 > 2.5 is true, and 2 == 2 is true.
    @test bg_value(columns, "Q3/y", 0.002) == 1.0      # op 2 is `<`
    @test bg_value(columns, "Q5/y", 0.003) == 1.0      # op 4 is `>`
    @test bg_value(columns, "Q1/y", 0.002) == 0.0      # op 0 is `==`
end
