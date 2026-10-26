# Golden test for `stdlib:sources/Scope` (plan section 8, M2 row: the editor-only scope
# sink), through the real pipeline (`parse` -> `flatten` -> `lower` -> `simulate`).
#
# A Scope is an editor object (D16): it names the signals to show in a plot panel and has no
# effect on the simulation. The block therefore carries its inputs through an internal
# `sink` copy, which keeps `block.check` clean (no unused declaration) without changing any
# source signal.
#
# Model: a Sine (1 rad/s) drives both a Scope and, in the second run, nothing at all.
# Reference: y(t) = sin(t); the scope's input and sink copy are the same signal, and the
# source is bit-identical with and without the scope attached.
#
# Tolerance: rtol 1e-6 against the analytic sine, and an exact comparison between the two
# runs (the scope contributes no dynamics: zero states).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: Scope sink (editor-only)" begin
    sine(t) = sin(t)

    scope_model = bg_model(
        "SineWithScope",
        [
            bg_node("n1", "Sine1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "1.0", "frequency" => "1.0",
                    "phase" => "0.0", "offset" => "0.0")),
            bg_node("n2", "Scope1", bg_ref("stdlib:sources/Scope")),
        ],
        [bg_conn("c1", "signal", "n1", "y", "n2", "u")];
        t_end = 1.0, points = 101,
    )
    plain_model = bg_model(
        "SineWithoutScope",
        [
            bg_node("n1", "Sine1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "1.0", "frequency" => "1.0",
                    "phase" => "0.0", "offset" => "0.0")),
        ],
        Any[];
        t_end = 1.0, points = 101,
    )

    columns, result, flat = bg_run(scope_model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 0                 # a scope adds no dynamics

    plain, plain_result, plain_flat = bg_run(plain_model)
    @test plain_result.status == "done"
    @test plain_flat.stats.states == 0

    for t in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "Sine1/y", t), sine(t); rtol = 1e-6,
            atol = 1e-9)
        # The scope sees exactly the source signal; its internal copy is a no-op.
        @test bg_value(columns, "Scope1/u[1]", t) == bg_value(columns, "Sine1/y", t)
        @test bg_value(columns, "Scope1/sink[1]", t) == bg_value(columns, "Sine1/y", t)
    end

    # Attaching the scope does not change the source: same grid, same values.
    @test columns["time"] == plain["time"]
    @test bg_all(columns, "Sine1/y") == bg_all(plain, "Sine1/y")
    @test maximum(abs.(bg_all(columns, "Sine1/y") .- sine.(columns["time"]))) < 1e-8
end
