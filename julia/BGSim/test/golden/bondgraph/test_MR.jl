# Golden test for `stdlib:bondgraph/MR` (plan section 8, M2 row: the modulated resistor),
# through the real pipeline (`flatten` → `simulate`).
#
# Model: a 1-junction carries an effort source Se = 12, the modulated resistor MR
# (resistance `gain*u`) and an inertia I (i = 1). The Step input switches u from 2 to 4 at
# t = 0.5 s, so the modulation really changes the dynamics at that instant.
#
# Reference: the analytic solution of the flat model.
#   * 1-junction: equal flows and efforts summing to zero, so
#     `12 = MR1/p.e + I1/p.e` and `f = MR1/p.f = I1/p.f`;
#   * MR: `MR1/p.e = gain*u*f`;  I: `I1/p.e = i*df/dt` (momentum P = i*f);
#   * phase 1 (u = 2, gain*u = 4):  f(t) = 3 (1 - e^(-4 t));
#   * phase 2 (u = 4, gain*u = 8):  f(t) = 3/2 + (f(0.5) - 3/2) e^(-8 (t - 0.5)).
#
# Tolerance: rtol 1e-6 against the analytic values (the run itself is at reltol 1e-10),
# including both phases and the switch instant, plus the junction power balance.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

@testset "golden: MR modulated resistor" begin
    gain = 2.0
    t_step = 0.5
    resistance(t) = gain * (t < t_step ? 2.0 : 4.0)          # gain*u(t)
    f1(t) = 3.0 * (1.0 - exp(-4.0 * t))                       # phase 1: f' = 12 - 4f
    f_switch = f1(t_step)
    f2(t) = 1.5 + (f_switch - 1.5) * exp(-8.0 * (t - t_step)) # phase 2: f' = 12 - 8f
    flow(t) = t <= t_step ? f1(t) : f2(t)

    model = bg_model(
        "MRDrivesInertia",
        [
            bg_node("n1", "Step1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => "0.5", "initial" => "2.0",
                    "final" => "4.0")),
            bg_node("n2", "MR1", bg_ref("stdlib:bondgraph/MR");
                params = Dict{String,Any}("gain" => "2.0")),
            bg_node("n3", "J1", bg_junction(1)),
            bg_node("n4", "Se1", bg_ref("stdlib:bondgraph/Se");
                params = Dict{String,Any}("e" => "12.0")),
            bg_node("n5", "I1", bg_ref("stdlib:bondgraph/I");
                params = Dict{String,Any}("i" => "1.0")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "bond", "n4", "p", "n3", nothing),
            bg_conn("c3", "bond", "n3", nothing, "n2", "p"),
            bg_conn("c4", "bond", "n3", nothing, "n5", "p"),
        ],
    )

    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    @test flat.stats.states == 1                 # the inertia momentum

    for t in (0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 1.0)
        f = flow(t)
        @test isapprox(bg_value(columns, "MR1/u", t), t < t_step ? 2.0 : 4.0; rtol = 1e-6)
        @test isapprox(bg_value(columns, "I1/p.f", t), f; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "MR1/p.f", t), f; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/P", t), f; rtol = 1e-6, atol = 1e-9)
        # The block: p.e ~ gain*u*p.f, with the resistance of the phase the point is in.
        @test isapprox(bg_value(columns, "MR1/p.e", t), resistance(t) * f; rtol = 1e-6,
            atol = 1e-9)
        # The 1-junction: the effort source supplies what the resistor dissipates plus what
        # the inertia stores.
        @test isapprox(bg_value(columns, "Se1/p.f", t), -f; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "I1/p.e", t), 12.0 - resistance(t) * f;
            rtol = 1e-6, atol = 1e-9)
        @test abs(
            bg_value(columns, "Se1/p.P", t) + bg_value(columns, "MR1/p.P", t) +
            bg_value(columns, "I1/p.P", t)
        ) <= 1e-8
    end

    # The whole recorded grid follows the analytic solution of both phases, including the
    # step at t = 0.5 s.
    times = columns["time"]
    @test maximum(abs.(bg_all(columns, "I1/p.f") .- flow.(times))) < 1e-6

    # At t = 0.5 s the modulated resistance has already switched: the state is continuous
    # (f(0.5) = f_switch), but the resistor effort jumps to the new resistance.
    @test isapprox(bg_value(columns, "I1/p.f", t_step), f_switch; rtol = 1e-6)
    @test isapprox(bg_value(columns, "MR1/p.e", t_step), 8.0 * f_switch; rtol = 1e-6)
end
