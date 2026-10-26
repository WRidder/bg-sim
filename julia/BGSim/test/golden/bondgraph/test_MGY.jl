# Golden test for `stdlib:bondgraph/MGY` (plan section 8, M2 row: the modulated gyrator),
# through the real pipeline (`flatten` → `simulate`).
#
# Model: a flow source Sf = -2 drives port p1, the Sine source u(t) = 2 + sin(3 t) is the
# modulus, and an inertia I (i = 1) sits on port p2. The flow source keeps every algebraic
# port variable at zero at t = 0 (see the MTF golden test for why that matters).
#
# Reference: the analytic solution of the flat model.
#   * the gyrator: `p1.e = -u*p2.f`, `p2.e = u*p1.f` (power conserving, the GY orientation
#     of plan 9.1);
#   * the flow source sets the primary flow: `p1.f = -Sf1/p.f = 2`;
#   * the inertia is driven through port p2: `p2.e = 2 u`, so `ddt(P) = 2 u` and
#     `P(t) = 2 ∫₀ᵗ u ds = 2 (2 t + (1 - cos(3 t))/3)`; `I1/p.f = P/i = P`, `p2.f = -P`;
#   * `p1.e = u P`, and `p1.e p1.f + p2.e p2.f = 0` on every sample.
#
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10),
# plus a whole-grid bound of 1e-8 and the gyrator's power balance.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: MGY modulated gyrator" begin
    u(t) = 2.0 + sin(3.0 * t)
    integral(t) = 2.0 * t + (1.0 - cos(3.0 * t)) / 3.0   # ∫₀ᵗ u, analytically
    momentum(t) = 2.0 * integral(t)                       # P = 2 ∫u, i = 1

    model = bg_model(
        "MGYDrivesInertia",
        [
            bg_node("n1", "Sine1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "1.0", "frequency" => "3.0",
                    "offset" => "2.0")),
            bg_node("n2", "MGY1", bg_ref("stdlib:bondgraph/MGY")),
            bg_node("n3", "Sf1", bg_ref("stdlib:bondgraph/Sf");
                params = Dict{String,Any}("f" => "-2.0")),
            bg_node("n4", "I1", bg_ref("stdlib:bondgraph/I");
                params = Dict{String,Any}("i" => "1.0")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n3", "p", "n2", "p1"),
            bg_conn("c3", "bond", "n2", "p2", "n4", "p"),
        ],
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                  # the inertia momentum

    for t in (0.0, 0.25, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "MGY1/u", t), u(t); rtol = 1e-6)
        # The block's own equations.
        @test isapprox(bg_value(columns, "MGY1/p1.f", t), 2.0; rtol = 1e-6)
        @test isapprox(bg_value(columns, "MGY1/p2.e", t), 2.0 * u(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "MGY1/p2.f", t), -momentum(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "MGY1/p1.e", t), u(t) * momentum(t); rtol = 1e-6,
            atol = 1e-9)
        # The inertia and the power-conserving pair of ports.
        @test isapprox(bg_value(columns, "I1/P", t), momentum(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/p.e", t), 2.0 * u(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/p.f", t), momentum(t); rtol = 1e-6,
            atol = 1e-9)
        @test abs(bg_value(columns, "MGY1/p1.P", t) + bg_value(columns, "MGY1/p2.P", t)) <=
              1e-8
    end

    # The whole recorded grid, not only the sample points (the modulus is time varying).
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "I1/P") .- momentum.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "MGY1/p2.e") .- 2.0 .* u.(times))) < 1e-8
end
