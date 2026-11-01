# Golden tests of `stdlib:contact/Tyre` (the vehicle tyre of the `cars` example).
#
# 1. Prescribed motion (tyre_rig.jl `_ty_kinematic`): the carrier moves at a set velocity with
#    its centre at a set height over the plane, the wheel spins at a set rate. After the
#    first-order patch deflection (Rill) has settled, the forces are the steady-state formulas:
#    the vertical force is kz times the deflection, the longitudinal and lateral forces are the
#    Magic Formula of the slips (pure and combined, friction ellipse), the slips are the ISO
#    definitions (kappa = (w Rl - Vx)/Vx, tan alpha = -Vsy/Vx).
# 2. A free wheel (`_ty_wheel`) coasting on the flat floor: rolling resistance decelerates it
#    at frr Fz R0 / (Rl (m + Ja/Rl^2)); the energy book (body, rotor, gravity, tyre springs and
#    the integral of the dissipated power) closes.
# 3. A free wheel on a TerrainSurface plane (25 %) rolls down at g sin(gam) / (1 + Ja/(m Rl^2))
#    (no rolling resistance) and the contact point stays on the plane.
using Test
using BGSim

if !isdefined(@__MODULE__, :_ty_kinematic)
    include(joinpath(@__DIR__, "tyre_rig.jl"))
end

@testset "Tyre (golden)" begin
    p = _TY_P
    z = 0.288                       # 12 mm deflection: Fz = 3000 N = Fz0
    Rl = z                          # the lowest rim point is on the plane: loaded radius = z
    Vx = 20.0

    @testset "free rolling: load, no force, no slip" begin
        cols, res, _ = bg_run(_ty_kinematic(; vx = Vx, w_rel = Vx / Rl, z))
        @test res.status == "done"
        @test isempty([d for d in res.diagnostics if d.code in ("W201", "W202", "W206")])
        @test isapprox(cols["Tyre/Fz"][end], p.kz * (p.R0 - z); rtol = 1.0e-6)
        @test isapprox(cols["Tyre/delta"][end], p.R0 - z; atol = 1.0e-9)
        @test isapprox(cols["Tyre/Vx"][end], Vx; atol = 1.0e-9)
        @test isapprox(cols["Tyre/omega"][end], Vx / Rl; atol = 1.0e-9)
        @test abs(cols["Tyre/kappa"][end]) < 1.0e-7     # the pose integrator drifts by ~1e-9 m
        @test abs(cols["Tyre/alpha"][end]) < 1.0e-9
        @test abs(cols["Tyre/Fx"][end]) < 1.0e-2
        @test abs(cols["Tyre/Fy"][end]) < 1.0e-5
        # the contact point under the centre, on the plane; the world force is the load
        @test abs(cols["Tyre/zc"][end]) < 1.0e-7
        @test isapprox(cols["Tyre/Fwz"][end], cols["Tyre/Fz"][end]; rtol = 1.0e-12)
    end

    @testset "pure and combined slip: the Magic Formula" begin
        Fz = p.kz * (p.R0 - z)
        for (kappa, tana) in ((0.03, 0.0), (-0.08, 0.0), (0.0, 0.05), (0.0, -0.2), (0.05, 0.05), (0.1, 0.15))
            w = (1 + kappa) * Vx / Rl
            vy = -tana * Vx                       # the patch slides right: the force points left
            cols, res, _ = bg_run(_ty_kinematic(; vx = Vx, vy, w_rel = w, z))
            @test res.status == "done"
            # the slips use sqrt(Vx^2 + vN^2) in the denominator
            Vr = sqrt(Vx^2 + p.vN^2)
            k_ref = (w * Rl - Vx) / Vr
            s_ref = -vy / Vr
            Fx, Fy = _ty_forces(Fz, k_ref, s_ref)
            @test isapprox(cols["Tyre/kappa"][end], k_ref; atol = 1.0e-7)
            @test isapprox(cols["Tyre/alpha"][end], atan(s_ref); atol = 1.0e-9)
            @test isapprox(cols["Tyre/Fx"][end], Fx; atol = 1.0e-3 * Fz)
            @test isapprox(cols["Tyre/Fy"][end], Fy; atol = 1.0e-3 * Fz)
        end
        # saturated combined slip: the resultant is on the friction ellipse
        cols, _, _ = bg_run(_ty_kinematic(; vx = Vx, vy = -0.4 * Vx, w_rel = 1.5 * Vx / Rl, z))
        mx = p.mux * (1 + p.dmu * 0.0)
        my = p.muy * (1 + p.dmu * 0.0)
        Fx, Fy = cols["Tyre/Fx"][end], cols["Tyre/Fy"][end]
        @test (Fx / (mx * Fz))^2 + (Fy / (my * Fz))^2 < 1.0
        @test (Fx / (mx * Fz))^2 + (Fy / (my * Fz))^2 > 0.6
    end

    @testset "friction scale mus" begin
        Fz = p.kz * (p.R0 - z)
        w = 1.1 * Vx / Rl
        cols, _, _ = bg_run(_ty_kinematic(; vx = Vx, w_rel = w, z, mus = 0.5))
        Vr = sqrt(Vx^2 + p.vN^2)
        Fx, _ = _ty_forces(Fz, (w * Rl - Vx) / Vr, 0.0; mus = 0.5)
        @test isapprox(cols["Tyre/Fx"][end], Fx; atol = 1.0e-3 * Fz)
        @test cols["Tyre/Fx"][end] < 0.5 * p.mux * Fz
    end

    @testset "coasting wheel: rolling resistance and the energy book" begin
        m, Ja, v0 = 300.0, 1.2, 10.0
        doc = _ty_wheel(; m, Ja, v = v0, t_end = 2.0, points = 401)
        cols, res, _ = bg_run(doc)
        @test res.status == "done"
        t = cols["time"]
        Fz = m * _TY_G0
        Rl0 = p.R0 - Fz / p.kz
        a = p.frr * Fz * p.R0 / (Rl0 * (m + Ja / Rl0^2))
        # after the patch transient: constant deceleration
        v(tk) = bg_value(cols, "Tyre/Vx", tk)
        @test isapprox((v(0.5) - v(1.5)) / 1.0, a; rtol = 2.0e-3)
        @test isapprox(cols["Tyre/Fz"][end], Fz; rtol = 1.0e-4)
        @test abs(cols["Pose/py"][end]) < 1.0e-9
        Eb = [0.5 * sum(cols["Carrier/inertia/P[$k]"][i] * cols["Pose/tw[$k]"][i] for k in 1:6) +
              m * _TY_G0 * cols["Pose/pz"][i] for i in eachindex(t)]
        E = Eb .+ cols["Wheel/Ek"] .+ cols["Tyre/Ec"] .+ _ty_cumint(t, cols["Tyre/Pd"])
        lost = E[1] - (Eb[end] + cols["Wheel/Ek"][end] + cols["Tyre/Ec"][end])
        @test lost > 0
        @test maximum(abs.(E .- E[1])) < 1.0e-4 * lost
        @test minimum(cols["Tyre/Pd"]) > -1.0e-6
    end

    @testset "rolling down a 25 % TerrainSurface plane" begin
        m, Ja, slope = 300.0, 1.2, 0.25
        gam = atan(slope)
        doc = _ty_wheel(; m, Ja, v = 0.0, slope, frr = 0.0, t_end = 2.0, points = 401)
        cols, res, _ = bg_run(doc)
        @test res.status == "done"
        Fz = m * _TY_G0 * cos(gam)
        Rl0 = p.R0 - Fz / p.kz
        a = _TY_G0 * sin(gam) / (1 + Ja / (m * Rl0^2))
        x(tk) = bg_value(cols, "Pose/px", tk)
        x0 = cols["Pose/px"][1]
        # down the slope (towards -x): s = a t^2/2 along the slope after a short settling
        s(tk) = (x0 - x(tk)) / cos(gam)
        @test isapprox(s(2.0) - s(1.0) - (0.5 * a * (4.0 - 1.0)), 0.0; atol = 2.0e-3 * 0.5 * a * 3.0)
        @test isapprox(cols["Tyre/Fz"][end], Fz; rtol = 2.0e-3)
        # the contact point is on the plane z = slope x, the force normal to it plus traction
        zc_err = maximum(abs.(cols["Tyre/zc"] .- slope .* cols["Tyre/xc"]))
        @test zc_err < 1.0e-6
    end
end
