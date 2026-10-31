# Golden test for `stdlib:converters/Electromagnet` (the variable-reluctance actuator of the
# maglev example), through the real pipeline.
#
# The block is a two-port IC-field with the stored energy W(lambda, h) = lambda^2/(2 L(h)),
# L(h) = L_inf + 2*alpha/(h + h0). Its port laws are i = lambda/L and the attraction
# F = alpha*i^2/(h + h0)^2 on the armature, and the power into its ports equals dW/dt.
#
# 1. Statics and the electrical transient (iconic wiring): a 10 V `VoltageSource` drives the
#    coil through a 2 Ohm `Resistor`, both flanges are `Fixed`, so the gap stays at 0.15 m
#    and L is constant: i(t) = V/R*(1 - exp(-R*t/L)), F = alpha*i^2/h^2, W = L*i^2/2,
#    lambda = L*i. At rest the force is that of the MathWorks maglev law, so the trim
#    current that carries a 20 g ball, sqrt(m*g/alpha)*h, gives F = m*g exactly.
# 2. Power continuity (bond graph): a 1-junction (coil current) with an `Se` voltage, an `R`
#    and the coil port; a 1-junction (ball velocity) with the gravity `Se`, the ball `I` and
#    the armature port; the stator is `Fixed`. The ball starts at the trim current of
#    h = 0.1 m but the voltage holds only 90 % of the trim current, so the ball drops away.
#    Checked: the port powers of the field sum to dW/dt (integrated over the run against
#    W(t) - W(0)), the ball obeys m*dv/dt = m*g - F, the gap integrates the ball velocity,
#    and Tellegen's sum of every port power is zero.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using .BondGraphGolden

const EMAG_alpha = 2.4832e-5      # H*m (N*m^2/A^2), the MathWorks maglev constant
const EMAG_Linf = 0.03            # H
const EMAG_m = 0.02               # kg
const EMAG_g = 9.81               # m/s^2

_emag_p(pairs...) = Dict{String,Any}(k => string(v) for (k, v) in pairs)

@testset "golden: Electromagnet" begin
    @testset "statics and the RL transient at a fixed gap" begin
        V, R, h = 10.0, 2.0, 0.15
        L = EMAG_Linf + 2 * EMAG_alpha / h
        model = bg_model(
            "ElectromagnetFixedGap",
            [
                bg_node("n1", "One", bg_ref("stdlib:sources/Constant"); params = _emag_p("value" => 1.0)),
                bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource"); params = _emag_p("V" => V)),
                bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor"); params = _emag_p("R" => R)),
                bg_node("n4", "EM", bg_ref("stdlib:converters/Electromagnet");
                    params = _emag_p("alpha" => EMAG_alpha, "L_inf" => EMAG_Linf),
                    starts = _emag_p("h" => h, "i" => 0.0)),
                bg_node("n5", "G1", bg_ref("stdlib:electrical/Ground")),
                bg_node("n6", "Stator", bg_ref("stdlib:translation/Fixed")),
                bg_node("n7", "Armature", bg_ref("stdlib:translation/Fixed")),
            ],
            [
                bg_conn("c1", "signal", "n1", "y", "n2", "u"),
                bg_conn("c2", "wire", "n2", "p", "n3", "p"),
                bg_conn("c3", "wire", "n3", "n", "n4", "p"),
                bg_conn("c4", "wire", "n4", "n", "n5", "p"),
                bg_conn("c5", "wire", "n2", "n", "n5", "p"),
                bg_conn("c6", "wire", "n4", "a", "n6", "a"),
                bg_conn("c7", "wire", "n4", "b", "n7", "a"),
            ];
            t_end = 0.2, points = 201,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        for t in (0.0, 0.01, 0.05, 0.2)
            i = V / R * (1 - exp(-R * t / L))
            @test isapprox(bg_value(columns, "EM/i", t), i; rtol = 1e-7, atol = 1e-10)
            @test isapprox(bg_value(columns, "EM/h", t), h; rtol = 1e-12)
            @test isapprox(bg_value(columns, "EM/L", t), L; rtol = 1e-12)
            @test isapprox(bg_value(columns, "EM/lambda", t), L * i; rtol = 1e-7, atol = 1e-10)
            @test isapprox(bg_value(columns, "EM/F", t), EMAG_alpha * i^2 / h^2; rtol = 1e-6, atol = 1e-12)
            @test isapprox(bg_value(columns, "EM/W", t), L * i^2 / 2; rtol = 1e-6, atol = 1e-12)
            # The armature port carries the attraction, the stator its reaction.
            @test isapprox(bg_value(columns, "EM/b.e", t), bg_value(columns, "EM/F", t); rtol = 1e-12)
            @test isapprox(bg_value(columns, "EM/a.e", t), -bg_value(columns, "EM/F", t); rtol = 1e-12)
            # No motion, so no mechanical power: all electrical power goes into the field.
            @test abs(bg_value(columns, "EM/P_mech", t)) <= 1e-12
        end
        # The trim law of the MathWorks model: i = sqrt(m g / alpha) h carries m g.
        for hb in (0.05, 0.15, 0.25)
            ib = sqrt(EMAG_m * EMAG_g / EMAG_alpha) * hb
            @test isapprox(EMAG_alpha * ib^2 / hb^2, EMAG_m * EMAG_g; rtol = 1e-12)
        end
    end

    @testset "power continuity with a free armature (bond graph)" begin
        h0, R = 0.1, 2.0
        i0 = sqrt(EMAG_m * EMAG_g / EMAG_alpha) * h0
        V = 0.9 * R * i0
        model = bg_model(
            "ElectromagnetBondGraph",
            [
                bg_node("e1", "Vs", bg_ref("stdlib:bondgraph/Se"); params = _emag_p("e" => V)),
                bg_node("e2", "Jc", bg_junction(1)),
                bg_node("e3", "Rc", bg_ref("stdlib:bondgraph/R"); params = _emag_p("r" => R)),
                bg_node("e4", "G1", bg_ref("stdlib:electrical/Ground")),
                bg_node("m0", "EM", bg_ref("stdlib:converters/Electromagnet");
                    params = _emag_p("alpha" => EMAG_alpha, "L_inf" => EMAG_Linf),
                    starts = _emag_p("h" => h0, "i" => i0)),
                bg_node("m1", "Jb", bg_junction(1)),
                bg_node("m2", "Grav", bg_ref("stdlib:bondgraph/Se"); params = _emag_p("e" => EMAG_m * EMAG_g)),
                bg_node("m3", "Ball", bg_ref("stdlib:bondgraph/I"); params = _emag_p("i" => EMAG_m)),
                bg_node("m4", "Frame", bg_ref("stdlib:translation/Fixed")),
            ],
            [
                bg_conn("b1", "bond", "e1", "p", "e2", nothing),
                bg_conn("b2", "bond", "e2", nothing, "e3", "p"),
                bg_conn("b3", "bond", "e2", nothing, "m0", "p"),
                bg_conn("w1", "wire", "m0", "n", "e4", "p"),
                bg_conn("b4", "bond", "m2", "p", "m1", nothing),
                bg_conn("b5", "bond", "m1", nothing, "m3", "p"),
                bg_conn("b6", "bond", "m1", nothing, "m0", "b"),
                bg_conn("w2", "wire", "m0", "a", "m4", "a"),
            ];
            t_end = 0.12, points = 1201,
        )
        columns, result, flat = bg_run(model)
        @test result.status == "done"
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        @test isempty([d for d in result.diagnostics if d.code == "W201"])
        t = columns["time"]
        W = bg_all(columns, "EM/W")
        Pel = bg_all(columns, "EM/P_el")
        Pm = bg_all(columns, "EM/P_mech")
        # The ball falls away: the gap grows and the current drops below the trim value.
        @test bg_value(columns, "EM/h", 0.12) > h0 + 1e-3
        @test bg_value(columns, "EM/i", 0.12) < i0
        # dW/dt = P_el + P_mech, integrated with Simpson's rule over pairs of the uniform
        # 0.1 ms output intervals (the run has no events, so every row is one grid time).
        @test length(t) == 1201
        P = Pel .+ Pm
        dt = t[2] - t[1]
        E = cumsum(vcat(0.0, [dt / 3 * (P[k] + 4 * P[k + 1] + P[k + 2]) for k in 1:2:length(t) - 2]))
        throughput = sum(dt .* (abs.(Pel) .+ abs.(Pm)))
        @test maximum(abs.(W[1:2:end] .- W[1] .- E)) <= 1e-7 * throughput
        # Port powers: P_el is the coil port, P_mech the gap port (stator at rest).
        for tk in (0.0, 0.03, 0.06, 0.12)
            @test isapprox(bg_value(columns, "EM/p.P", tk) + bg_value(columns, "EM/n.P", tk),
                bg_value(columns, "EM/P_el", tk); rtol = 1e-9, atol = 1e-12)
            @test isapprox(bg_value(columns, "EM/a.P", tk) + bg_value(columns, "EM/b.P", tk),
                bg_value(columns, "EM/P_mech", tk); rtol = 1e-9, atol = 1e-12)
            # Ball: m dv/dt = m g - F (the I element's effort is dP/dt).
            @test isapprox(bg_value(columns, "Ball/p.e", tk),
                EMAG_m * EMAG_g - bg_value(columns, "EM/F", tk); rtol = 1e-9, atol = 1e-12)
            # The armature moves with the ball.
            @test isapprox(bg_value(columns, "EM/b.f", tk), bg_value(columns, "Ball/p.f", tk);
                rtol = 1e-12, atol = 1e-15)
        end
        # The gap integrates the ball velocity.
        v = bg_all(columns, "Ball/p.f")
        h = bg_all(columns, "EM/h")
        x = h0 .+ cumsum(vcat(0.0, diff(t) .* (v[1:end-1] .+ v[2:end]) ./ 2))
        @test maximum(abs.(h .- x)) <= 1e-8
        # Tellegen: every bond carries opposite powers at its two ends.
        powers = [k for k in keys(columns) if endswith(k, ".P")]
        total = sum(bg_all(columns, k) for k in powers)
        @test maximum(abs.(total)) <= 1e-9 * maximum(abs.(Pel))
    end
end
