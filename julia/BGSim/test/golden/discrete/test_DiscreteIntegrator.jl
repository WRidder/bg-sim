# Golden test for `stdlib:discrete/DiscreteIntegrator` (plan section 8, M2 row: Discrete
# integrator), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a Constant 1 drives four integrators on a 1 ms clock, one per integration method plus
# one with an output limit.
#
# Reference: the block's own recurrence with Ts = 1e-3 and u = 1, written out in the test in
# the same operation order as the generated code:
#   forward:     i = i + Ts * up        (up is the input of the previous tick, 0 at first)
#   backward:    i = i + Ts * u
#   trapezoidal: i = i + (Ts * (u + up)) / 2
#   y = clamp(i, lower, upper)
# The values are compared with `==`: every operation is the same Float64 operation in the
# same order, so the sequences are bit-exact.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: DiscreteIntegrator" begin
    Ts, u = 1.0e-3, 1.0

    # The reference sequences, one per instance, exactly as the block computes them.
    function integrate(method; lower = -1.0e30, upper = 1.0e30)
        i, up = 0.0, 0.0
        values = Float64[i]
        for _ in 1:8
            if method == 0
                i = i + Ts * up
            elseif method == 1
                i = i + Ts * u
            else
                i = i + (Ts * (u + up)) / 2.0
            end
            y = i < lower ? lower : (i > upper ? upper : i)
            push!(values, y)
            up = u
        end
        return values
    end

    params(method; lower = "-1.0e30", upper = "1.0e30") = Dict{String,Any}(
        "method" => string(method), "lower" => lower, "upper" => upper,
    )

    model = dg_model(
        "DiscreteIntegratorMethods",
        [
            dg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            dg_node("n2", "F", bg_ref("stdlib:discrete/DiscreteIntegrator");
                params = params(0)),
            dg_node("n3", "B", bg_ref("stdlib:discrete/DiscreteIntegrator");
                params = params(1)),
            dg_node("n4", "T", bg_ref("stdlib:discrete/DiscreteIntegrator");
                params = params(2)),
            dg_node("n5", "L", bg_ref("stdlib:discrete/DiscreteIntegrator");
                params = params(1; upper = "0.0025")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n1", "y", "n3", "u"),
            bg_conn("c3", "signal", "n1", "y", "n4", "u"),
            bg_conn("c4", "signal", "n1", "y", "n5", "u"),
        ];
        t_end = 0.008, points = 9,
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0                 # the integral is a held value

    grid = dg_grid(0.008; points = 9)
    @test dg_values(columns, "F/y", grid) == integrate(0)
    @test dg_values(columns, "B/y", grid) == integrate(1)
    @test dg_values(columns, "T/y", grid) == integrate(2)
    @test dg_values(columns, "L/y", grid) == integrate(1; upper = 0.0025)

    # The literal first steps of each method, so the test does not only compare two
    # implementations of the same loop.
    @test dg_values(columns, "F/y", grid)[3] == 0.001          # forward skips the first sample
    @test dg_values(columns, "B/y", grid)[2] == 0.001
    @test dg_values(columns, "T/y", grid)[2] == 0.0005         # half a step at the first tick
    @test dg_values(columns, "L/y", grid)[5] == 0.0025         # clamped at the upper limit
    @test dg_values(columns, "L/y", grid)[9] == 0.0025
    # The limit clamps the output only: the integral state keeps growing.
    @test bg_value(columns, "L/i", 0.008) == integrate(1)[9]
end
