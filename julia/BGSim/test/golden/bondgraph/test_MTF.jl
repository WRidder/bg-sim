# Golden test for `stdlib:bondgraph/MTF` (plan section 8, M2 row: the modulated
# transformer), through the real pipeline (`flatten` → `simulate`).
#
# Model: a flow source Sf = -2 drives port p1, the Sine source u(t) = 2 + sin(3 t) is the
# modulus, and a capacitor C (c = 1) sits on port p2 — the transformer charging a capacitor
# is the dual of the gyrator driving an inertia (see `test_MGY.jl`). A flow source is used
# on purpose: an effort source would force the transformer's secondary effort to a non-zero
# value at t = 0, which makes the algebraic port variable's start inconsistent at
# initialization.
#
# Reference: the analytic solution of the flat model.
#   * the transformer: `p1.e = u*p2.e`, `p2.f = -u*p1.f` (power conserving);
#   * the flow source sets the primary flow: `p1.f = -Sf1/p.f = 2`;
#   * the secondary flow charges the capacitor: `C1/p.f = -p2.f = 2 u`, hence
#     `q(t) = 2 ∫₀ᵗ u ds = 2 (2 t + (1 - cos(3 t))/3)` and `p2.e = C1/p.e = q/c = q`;
#   * `p1.e = u q`, and `p1.e p1.f + p2.e p2.f = 0` on every sample.
#
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10),
# plus a whole-grid bound of 1e-8 and the transformer's power balance.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: MTF modulated transformer" begin
    u(t) = 2.0 + sin(3.0 * t)
    integral(t) = 2.0 * t + (1.0 - cos(3.0 * t)) / 3.0   # ∫₀ᵗ u, analytically
    charge(t) = 2.0 * integral(t)                         # q = 2 ∫u, c = 1

    model = bg_model(
        "MTFChargesC",
        [
            bg_node("n1", "Sine1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "1.0", "frequency" => "3.0",
                    "offset" => "2.0")),
            bg_node("n2", "MTF1", bg_ref("stdlib:bondgraph/MTF")),
            bg_node("n3", "Sf1", bg_ref("stdlib:bondgraph/Sf");
                params = Dict{String,Any}("f" => "-2.0")),
            bg_node("n4", "C1", bg_ref("stdlib:bondgraph/C");
                params = Dict{String,Any}("c" => "1.0")),
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
    @test flat.stats.states == 1                  # the capacitor charge

    for t in (0.0, 0.25, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "MTF1/u", t), u(t); rtol = 1e-6)
        # The block's own equations.
        @test isapprox(bg_value(columns, "MTF1/p2.e", t), charge(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "MTF1/p2.f", t), -2.0 * u(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "MTF1/p1.f", t), 2.0; rtol = 1e-6)
        @test isapprox(bg_value(columns, "MTF1/p1.e", t), u(t) * charge(t); rtol = 1e-6,
            atol = 1e-9)
        # The capacitor and the power-conserving pair of ports.
        @test isapprox(bg_value(columns, "C1/q", t), charge(t); rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "C1/p.f", t), 2.0 * u(t); rtol = 1e-6,
            atol = 1e-9)
        @test isapprox(bg_value(columns, "C1/p.e", t), charge(t); rtol = 1e-6, atol = 1e-9)
        @test abs(bg_value(columns, "MTF1/p1.P", t) + bg_value(columns, "MTF1/p2.P", t)) <=
              1e-8
        @test bg_value(columns, "MTF1/p1.f", t) * bg_value(columns, "MTF1/p2.f", t) <= 0.0
    end

    # The whole recorded grid, not only the sample points (the modulus is time varying).
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "C1/q") .- charge.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "MTF1/p2.e") .- charge.(times))) < 1e-8
end
