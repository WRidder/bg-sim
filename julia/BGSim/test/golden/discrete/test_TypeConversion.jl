# Golden test for `stdlib:discrete/TypeConversion` (plan section 8, M2 row: Type conversion),
# through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: two discrete test ramps on a 1 ms clock, one counting up by 0.75 and one down by
# 0.25, each converted to all three targets (Real 0, Int 1, Bool 2).
#
# Reference: Real is the identity, Int truncates toward zero (floor for x >= 0, ceil for
# x < 0), Bool is 1 for a non-zero value and 0 for zero. The recorded signal is a Float64
# (plan 3.5), so a Bool appears as 1/0 and an Int as its integer value; the comparison is `==`.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: TypeConversion" begin
    as_int(x) = x >= 0 ? floor(x) : ceil(x)
    as_bool(x) = x == 0 ? 0.0 : 1.0

    function ramp(increment, n)
        values = Float64[0.0]
        acc = 0.0
        for _ in 1:n
            acc = acc + increment
            push!(values, acc)
        end
        return values
    end

    nodes = Any[
        dg_node("n1", "UP", Dict{String,Any}("inline" =>
            Dict{String,Any}("source" => dg_ramp(increment = 0.75)))),
        dg_node("n2", "DN", Dict{String,Any}("inline" =>
            Dict{String,Any}("source" => dg_ramp(increment = -0.25)))),
    ]
    connections = Any[]
    for (ref, node, target) in (("UR", "n1", 0), ("UI", "n1", 1), ("UB", "n1", 2),
        ("DR", "n2", 0), ("DI", "n2", 1), ("DB", "n2", 2))
        push!(nodes, dg_node(ref, ref, bg_ref("stdlib:discrete/TypeConversion");
            params = Dict{String,Any}("target" => string(target))))
        push!(connections, bg_conn("c$ref", "signal", node, "y", ref, "u"))
    end

    model = dg_model("TypeConversionTargets", nodes, connections; t_end = 0.008, points = 9)
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    up, down = ramp(0.75, 8), ramp(-0.25, 8)
    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "UR/y", grid) == up
    @test dg_values(columns, "UI/y", grid) == as_int.(up)
    @test dg_values(columns, "UB/y", grid) == as_bool.(up)
    @test dg_values(columns, "DR/y", grid) == down
    @test dg_values(columns, "DI/y", grid) == as_int.(down)
    @test dg_values(columns, "DB/y", grid) == as_bool.(down)

    # The literal sequences: 0, 0.75, 1.5, 2.25, 3.0, ... truncates to 0, 0, 1, 2, 3, ...
    @test as_int.(up) == Float64[0, 0, 1, 2, 3, 3, 4, 5, 6]
    @test as_bool.(up) == Float64[0, 1, 1, 1, 1, 1, 1, 1, 1]
    # Negative values truncate toward zero, not down: -0.25 and -0.5 become -0.0.
    @test as_int.(down) == Float64[0, -0.0, -0.0, -0.0, -1, -1, -1, -1, -2]
    @test as_int.(-0.5) == -0.0
    @test as_int.(-1.5) == -1.0
    @test as_bool.(down) == Float64[0, 1, 1, 1, 1, 1, 1, 1, 1]
end
