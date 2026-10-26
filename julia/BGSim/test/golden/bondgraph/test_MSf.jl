# Golden test for `stdlib:bondgraph/MSf` (plan section 8, M2 row: the modulated flow
# source), through the real pipeline (`flatten` → `simulate`).
#
# Model: a Sine source u(t) = 2 + sin(3 t) modulates the flow source, which charges the
# capacitor C through a 0-junction. Reference: the analytic solution of the flat model.
#
#   * MSf imposes its port flow, so `MSf1/p.f = gain*u` (the block's own equation);
#   * a port flow is positive into its element, so the flow source that drives the junction
#     carries `MSf1/p.f = gain*u` with `gain = -1` while the capacitor receives `+u`;
#   * the 0-junction sums the port flows to zero, so `C1/p.f = u = 2 + sin(3 t)`;
#   * the capacitor integrates it: `q(t) = ∫₀ᵗ u ds = 2 t + (1 - cos(3 t))/3`, and
#     `C1/p.e = q/c = 2 q` with `c = 0.5`.
#
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10), plus
# a whole-grid bound of 1e-8 and the power balance of the 0-junction.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: MSf modulated flow source" begin
    u(t) = 2.0 + sin(3.0 * t)
    charge(t) = 2.0 * t + (1.0 - cos(3.0 * t)) / 3.0     # ∫₀ᵗ u, analytically
    c = 0.5

    model = bg_model(
        "MSfChargesC",
        [
            bg_node("n1", "Sine1", bg_ref("stdlib:sources/Sine");
                params = Dict{String,Any}("amplitude" => "1.0", "frequency" => "3.0",
                    "offset" => "2.0")),
            bg_node("n2", "MSf1", bg_ref("stdlib:bondgraph/MSf");
                params = Dict{String,Any}("gain" => "-1.0")),
            bg_node("n3", "J0", bg_junction(0)),
            bg_node("n4", "C1", bg_ref("stdlib:bondgraph/C");
                params = Dict{String,Any}("c" => "0.5")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n2", "p", "n3", nothing),
            bg_conn("c3", "bond", "n3", nothing, "n4", "p"),
        ],
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the capacitor charge

    for t in (0.0, 0.25, 0.5, 0.75, 1.0)
        @test isapprox(bg_value(columns, "Sine1/y", t), u(t); rtol = 1e-6)
        @test isapprox(bg_value(columns, "MSf1/u", t), u(t); rtol = 1e-6)
        # The block: p.f ~ gain*u, with gain = -1.
        @test isapprox(bg_value(columns, "MSf1/p.f", t), -u(t); rtol = 1e-6, atol = 1e-9)
        # The 0-junction: the capacitor sees the negated source flow.
        @test isapprox(bg_value(columns, "C1/p.f", t), u(t); rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "C1/q", t), charge(t); rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "C1/p.e", t), charge(t) / c; rtol = 1e-6,
            atol = 1e-9)
        # Power is conserved across the junction pair (D15 records e*f as p.P).
        @test abs(bg_value(columns, "MSf1/p.P", t) + bg_value(columns, "C1/p.P", t)) <=
              1e-8
    end

    # The whole recorded grid, not only the sample points: q(t) and e(t) follow the
    # analytic integral everywhere.
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "C1/q") .- charge.(times))) < 1e-8
    @test maximum(abs.(bg_all(columns, "C1/p.e") .- charge.(times) ./ c)) < 1e-8
end
