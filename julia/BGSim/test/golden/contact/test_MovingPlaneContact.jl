# Golden test for `stdlib:contact/MovingPlaneContact` (a sphere on a spatial body against a
# finite face carried by a translating carrier and slid by a Translation port), through the
# real pipeline (`parse` -> `flatten` -> `simulate`, Rodas5P, reltol 1e-8).
#
# Belt rig (the carrier moves the face, the slide is fixed):
#   * rest: f_n = m g and the Hertz penetration (x = (F sqrt(xref)/k)^(2/3)); the ball does
#     not move (|v| < 1e-9).
#   * a belt step to V at t_belt: the friction torque r x F spins the ball up until it rolls;
#     a solid sphere then rolls at v = 2V/7 with w_y = -(5V/7)/r (angular-momentum balance about
#     the contact point). Rolling needs no friction, so this is exact up to the solver error
#     (checked to 1e-4 relative).
#   * the finite face: the ball falls off the back edge once the face has moved w1 further
#     than the ball, at t_belt + w1 / (5V/7) (the edge gate).
#   * power: p.P + j.P + Pc = gate Fk xd + Pd at every sample (the storage rate of the gated
#     spring plus the dissipation), integrated over the run to the stored energy.
# Clamp rig (the slide port drives both jaws, the carrier is at rest):
#   * each jaw carries half the slide force (sum of j.e = the source force);
#   * hold: below the slip threshold the ball creeps at s = vs atanh(m g / (2 mu f_n)), the
#     regularisation error of the isotropic friction (checked to 2 %);
#   * slide: past the threshold F = m g / mu the ball accelerates at a = g - mu F(t) / m; the
#     speed after the crossing is 5 (t - t*)^2 for the ramp of the rig (checked to 1 cm/s,
#     the regularisation lag of a few vs).
#   * no spin: the two friction torques about the centre cancel (|w| < 1e-6 rad/s, the solver noise).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :MovingContactRigs)
    include(joinpath(@__DIR__, "moving_contact_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
using .MovingContactRigs
import BGSim.Library

@testset "MovingPlaneContact (golden)" begin
    blocks = Dict(b.ref => b for b in Library.load_stdlib())

    @testset "catalog: Contact group, clean block, ports and units" begin
        b = blocks["stdlib:contact/MovingPlaneContact"]
        @test b.group == "Contact"
        @test b.icon == "ct-moving-plane-contact"
        @test !isempty(b.description)
        @test isempty(check_block(b.ast))
        bal = block_balance(b.ast)
        @test bal.unknowns == bal.equations
        @test [(p.name, p.domain) for p in b.interface.ports] == [("p", "Spatial"), ("j", "Translation")]
        @test b.interface.causality == [(ports = ["p"], kind = "fixed", value = "effort_out"),
                                        (ports = ["j"], kind = "fixed", value = "effort_out")]
        for d in b.interface.parameters
            @test !isempty(d.description)
        end
        env = BGSim.Units.unit_env(b.ast)
        for k in 1:3
            @test env.labels[Symbol("p.e[", k, "]")] == "N*m"
            @test env.labels[Symbol("p.e[", k + 3, "]")] == "N"
        end
        @test env.labels[Symbol("j.e")] == "N"
        @test env.labels[Symbol("j.f")] == "m/s"
    end

    @testset "belt: rest, rolling at 2V/7, falling off the edge, power" begin
        V, tb, w1 = 0.2, 0.3, 0.08
        cols, res, _ = bg_run(mpc_belt_model(V = V, t_belt = tb, w1 = w1))
        @test res.status == "done"
        t = cols["time"]
        # rest
        Fw = MPC_M * MPC_G0
        @test bg_value(cols, "Belt/f_n", 0.25) ≈ Fw rtol = 1e-5
        @test bg_value(cols, "Belt/delta", 0.25) ≈ mpc_x_of_force(Fw) rtol = 1e-4
        @test abs(bg_value(cols, "Pose/g[5]", 0.25)) < 1e-9
        # rolling: v = 2V/7 and w_y = -(5V/7)/r; the world velocity is the pose rate
        i1, i2 = findlast(<=(0.55), t), findlast(<=(0.65), t)
        vx = (cols["Pose/g[5]"][i2] - cols["Pose/g[5]"][i1]) / (t[i2] - t[i1])
        @test vx ≈ 2V / 7 rtol = 1e-4
        # the port flow is the point twist (WP-O3a), and w_y is the same in the body-aligned
        # point frame
        @test bg_value(cols, "Belt/p.f[2]", 0.6) ≈ -(5V / 7) / MPC_R rtol = 1e-4
        @test abs(bg_value(cols, "Belt/slip", 0.6)) < 1e-5
        @test bg_value(cols, "Belt/f_n", 0.6) ≈ Fw rtol = 1e-4
        # the edge: the contact point leaves the face at u1 = -w1
        t_edge = tb + 0.0117 + (w1 - 0.0117 * 0.5 * 5V / 7) / (5V / 7)   # slip phase ~ 11.7 ms
        @test bg_value(cols, "Belt/gate", round(t_edge - 0.05; digits = 3)) > 0.99
        @test bg_value(cols, "Belt/gate", round(t_edge + 0.05; digits = 3)) < 1e-3
        @test bg_value(cols, "Pose/g[7]", 1.2) < MPC_R - 0.05            # fell off
        # power: port powers plus the carrier power = gated spring storage rate + dissipation
        pin = cols["Belt/p.P"] .+ cols["Belt/j.P"] .+ cols["Belt/Pc"]
        tail = findall(<=(0.8), t)
        Ein = sum(0.5 * (pin[k] + pin[k + 1]) * (t[k + 1] - t[k]) for k in tail[1:end - 1])
        Ed = sum(0.5 * (cols["Belt/Pd"][k] + cols["Belt/Pd"][k + 1]) * (t[k + 1] - t[k]) for k in tail[1:end - 1])
        dEc = cols["Belt/Ec"][tail[end]] - cols["Belt/Ec"][1]
        @test abs(Ein - Ed - dEc) < 1e-3 * max(abs(Ed), 1e-6)
    end

    @testset "clamp: half the slide force per jaw, creep law, sliding acceleration" begin
        mu, F0, tr, rate = 0.5, 20.0, 0.2, 10.0
        cols, res, _ = bg_run(mpc_clamp_model(F0 = F0, t_ramp = tr, rate = rate, mu = mu))
        @test res.status == "done"
        t = cols["time"]
        Fsrc(tk) = F0 - rate * max(tk - tr, 0.0)
        for tk in (0.1, 0.6, 1.0)
            @test bg_value(cols, "JawA/f_n", tk) ≈ Fsrc(tk) / 2 rtol = 2e-3
            @test bg_value(cols, "JawB/f_n", tk) ≈ Fsrc(tk) / 2 rtol = 2e-3
            @test bg_value(cols, "JawA/j.e", tk) + bg_value(cols, "JawB/j.e", tk) ≈ Fsrc(tk) rtol = 2e-3
        end
        # creep while held: s = vs atanh(rho), rho = m g / (2 mu f_n)
        for tk in (0.6, 1.0)
            rho = MPC_M * MPC_G0 / (mu * Fsrc(tk))
            @test bg_value(cols, "JawA/slip", tk) ≈ 1.0e-3 * atanh(rho) rtol = 2e-2
        end
        # sliding past the threshold F* = m g / mu: v_down = (rate mu / (2 m)) (t - t*)^2
        tstar = tr + (F0 - MPC_M * MPC_G0 / mu) / rate
        i1, i2 = findlast(<=(1.495), t), findlast(<=(1.5), t)
        vz = (cols["Pose/g[7]"][i2] - cols["Pose/g[7]"][i1]) / (t[i2] - t[i1])
        @test -vz ≈ rate * mu / (2 * MPC_M) * (1.4975 - tstar)^2 atol = 0.01
        # no spin
        for k in 1:3   # the angular part of the point twist (minus the port flow): solver noise only
            @test maximum(abs.(bg_all(cols, "JawA/p.f[$k]"))) < 1e-6
        end
    end
end
