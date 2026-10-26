# Golden test for `stdlib:continuous/Switch` (plan section 8, M2 row: switch), through the
# real pipeline.
#
# Model: u1 = 2, u2 = -3, ctrl = a Ramp from -1 with slope 1, threshold 0. The switch picks
# u1 while ctrl > 0 and u2 otherwise, so y = -3 until t = 1 and +2 after it.
#
# Reference: the analytic step of the control. Tolerance: atol 1e-9 (the values are constant).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Switch" begin
    model = bg_model(
        "SwitchOnRampControl",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "2.0")),
            bg_node("n2", "C2", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "-3.0")),
            bg_node("n3", "R1", bg_ref("stdlib:sources/Ramp");
                params = Dict{String,Any}(
                    "t_start" => "0.0", "slope" => "1.0", "initial" => "-1.0")),
            bg_node("n4", "W1", bg_ref("stdlib:continuous/Switch");
                params = Dict{String,Any}("threshold" => "0.0")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n4", "u1"),
            bg_conn("c2", "signal", "n2", "y", "n4", "u2"),
            bg_conn("c3", "signal", "n3", "y", "n4", "ctrl"),
        ];
        t_end = 2.0, points = 201,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0

    for t in (0.0, 0.25, 0.5, 0.9)
        @test isapprox(bg_value(columns, "W1/y", t), -3.0; atol = 1e-9)
    end
    for t in (1.1, 1.5, 2.0)
        @test isapprox(bg_value(columns, "W1/y", t), 2.0; atol = 1e-9)
    end
end
