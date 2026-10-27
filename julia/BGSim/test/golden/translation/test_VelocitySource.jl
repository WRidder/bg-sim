# Golden test for `stdlib:translation/VelocitySource` (plan section 8, M2 row: Velocity
# source), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# Model: a `Constant` drives the source input `u`, the source's single port `a` is wired to a
# `Damper` whose other port is `Fixed`. In D8's Translation convention the across variable is
# the velocity `f` and the through variable the force `e`, and a wire equates the across
# variables while summing the through variables to zero. The block imposes `a.f = v*u`
# (fixed flow-out causality, D6), so with `b.f = 0`
#
#   Damper.a.e = d*(v*u),  VelocitySource.a.e = -d*(v*u),  Fixed.a.e = +d*(v*u).
#
# The second model replaces the Constant with a `Step` (1 -> 3 at t = 2 ms) to prove the
# time-varying signal-input path. A `Spring` is added in parallel with the damper so the
# model keeps one state: a zero-state model whose only time dependence is a `t`-conditional
# source cannot be stepped yet (NOTE-4 item 3, an unrelated platform gap), and the spring
# integrates the imposed velocity, x(t) = v*integral(u dt).
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

function velocity_source_model(source)
    return bg_model(
        "VelocitySourceDrivesDamper",
        [
            source,
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "2.0")),
            bg_node("n3", "D1", bg_ref("stdlib:translation/Damper");
                params = Dict{String,Any}("d" => "500.0")),
            bg_node("n4", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.004, points = 101,
    )
end

@testset "golden: VelocitySource" begin
    const_source = bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
        params = Dict{String,Any}("value" => "1.5"))
    columns, result, flat = bg_run(velocity_source_model(const_source))
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 0                 # a pure algebraic source model

    v = 2.0                    # m/s per unit input
    d = 500.0                  # N*s/m
    u = 1.5
    flow = v * u
    force = d * flow
    for t in (0.0, 1.0e-3, 2.0e-3, 4.0e-3)
        @test isapprox(bg_value(columns, "C1/y", t), u; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/u", t), u; rtol = 1e-9)
        # The block and the wire to the damper set the same velocity.
        @test isapprox(bg_value(columns, "V1/a.f", t), flow; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/a.f", t), flow; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/b.f", t), 0.0; atol = 1e-12)
        # The damper reacts with d*v and the source absorbs the reaction.
        @test isapprox(bg_value(columns, "D1/a.e", t), force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "D1/b.e", t), -force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.e", t), -force; rtol = 1e-9)
        @test isapprox(bg_value(columns, "F1/a.e", t), force; rtol = 1e-9)
        # Power: the source delivers d*v^2 and the damper dissipates exactly that.
        @test isapprox(bg_value(columns, "D1/a.P", t), force * flow; rtol = 1e-9)
        @test isapprox(bg_value(columns, "V1/a.P", t), -force * flow; rtol = 1e-9)
        @test abs(bg_value(columns, "V1/a.P", t) + bg_value(columns, "D1/a.P", t) +
                  bg_value(columns, "D1/b.P", t) + bg_value(columns, "F1/a.P", t)) <= 1e-9
    end

    # The Step input path: u = 1 before 2 ms and u = 3 after it, so the source flow follows
    # the step and the spring in parallel integrates it. With the step at t_s = 2 ms,
    #   x(t) = v*t for t <= t_s, and x(t) = v*(t_s + 3*(t - t_s)) after it.
    v = 2.0
    d = 500.0
    k = 1000.0
    t_s = 2.0e-3
    step_model = bg_model(
        "VelocitySourceDrivesDamperAndSpring",
        [
            bg_node("n1", "S1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}(
                    "t_step" => "2.0e-3", "initial" => "1.0", "final" => "3.0")),
            bg_node("n2", "V1", bg_ref("stdlib:translation/VelocitySource");
                params = Dict{String,Any}("v" => "2.0")),
            bg_node("n3", "D1", bg_ref("stdlib:translation/Damper");
                params = Dict{String,Any}("d" => "500.0")),
            bg_node("n5", "SP1", bg_ref("stdlib:translation/Spring");
                params = Dict{String,Any}("k" => "1000.0")),
            bg_node("n4", "F1", bg_ref("stdlib:translation/Fixed")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "a", "n5", "a"),
            bg_conn("c4", "wire", "n3", "b", "n4", "a"),
            bg_conn("c5", "wire", "n5", "b", "n4", "a"),
        ];
        t_end = 4.0e-3, points = 101,
    )
    step_columns, step_result, step_flat = bg_run(step_model)
    @test step_result.status == "done"
    @test isempty([e for e in step_result.diagnostics if e.severity == "error"])
    @test step_flat.stats.states == 1             # the spring displacement
    for (t, input) in ((1.0e-3, 1.0), (3.0e-3, 3.0))
        x = t <= t_s ? v * t : v * (t_s + 3.0 * (t - t_s))
        @test isapprox(bg_value(step_columns, "S1/y", t), input; rtol = 1e-9)
        @test isapprox(bg_value(step_columns, "V1/u", t), input; rtol = 1e-9)
        @test isapprox(bg_value(step_columns, "V1/a.f", t), v * input; rtol = 1e-9)
        @test isapprox(bg_value(step_columns, "D1/a.f", t), v * input; rtol = 1e-9)
        @test isapprox(bg_value(step_columns, "SP1/a.f", t), v * input; rtol = 1e-9)
        @test isapprox(bg_value(step_columns, "SP1/x", t), x; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(step_columns, "D1/a.e", t), d * v * input; rtol = 1e-9)
        @test isapprox(bg_value(step_columns, "SP1/a.e", t), k * x; rtol = 1e-6)
        # The source absorbs both reaction forces of the wire node.
        @test isapprox(bg_value(step_columns, "V1/a.e", t),
            -(d * v * input + k * x); rtol = 1e-6)
    end
end
