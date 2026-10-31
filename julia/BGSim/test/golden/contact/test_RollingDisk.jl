# Golden tests of `stdlib:contact/RollingDisk` (the rolling contact of the `gyrover` example).
#
# The rig (rolling_rig.jl) is a free wheel body on the plane z = 0, started at the static
# penetration of its weight, so there is no landing transient. Each case has a closed form:
#
#   1. rolling straight: a wheel rolling without slip keeps its speed (no rolling resistance in
#      steady rolling: the penetration is constant, so the Hunt-Crossley damper does no work),
#      the slip stays at zero and the normal force equals the weight;
#   2. spinning start: a wheel spinning at w0 without forward speed slides; Coulomb friction
#      mu m g accelerates it, v = mu g t, until it rolls at v* = w0 R J/(J + m R^2) at
#      t* = w0 R / (mu g (1 + m R^2/J)); the contact dissipates exactly the lost energy;
#   3. drilling damping: an upright wheel turning about the vertical decays as
#      exp(-bsp t / J_t) (the contact point is on the spin axis, so friction does no work);
#   4. energy book in every case: body energy + spring energy + integral of the dissipated
#      power is constant (port power = dEc/dt + Pd).
#
# Tolerances: the regularised friction `mu f_n s / sqrt(s^2 + vs^2)` departs from Coulomb by
# (vs/s)^2/2 (1e-6 at s = 1 m/s); the creep that a rolling wheel needs for zero tangential force
# is zero; the integrators run at reltol 1e-9.
using Test
using BGSim

if !isdefined(@__MODULE__, :_rr_wheel)
    include(joinpath(@__DIR__, "rolling_rig.jl"))
end

@testset "RollingDisk (golden)" begin
    @testset "rolls straight at constant speed without slip" begin
        m, R, J = 2.0, 0.2, (0.02, 0.02, 0.04)
        doc = _rr_wheel(; m, R, J, v = 1.0, t_end = 2.0, points = 401)
        cols, res, _ = bg_run(doc)
        @test res.status == "done"
        @test isempty([d for d in res.diagnostics if d.code in ("W201", "W206")])
        t = cols["time"]
        @test isapprox(cols["Pose/px"][end], 2.0; atol = 1.0e-6)
        @test maximum(abs, cols["Pose/py"]) < 1.0e-9
        @test maximum(abs, cols["Tyre/s_lon"]) < 1.0e-7
        @test maximum(abs, cols["Tyre/s_lat"]) < 1.0e-9
        @test maximum(abs.(cols["Tyre/f_n"] .- m * _RR_G0)) < 1.0e-4 * m * _RR_G0
        @test maximum(abs, cols["Tyre/camber"]) < 1.0e-9
        # the contact point runs under the centre, on the plane
        @test maximum(abs.(cols["Tyre/xc"] .- cols["Pose/px"])) < 1.0e-9
        @test maximum(abs, cols["Tyre/zc"]) < 2.0e-4
        E = _rr_body_energy(cols, m) .+ cols["Tyre/Ec"] .+ _rr_cumint(t, cols["Tyre/Pd"])
        @test maximum(abs.(E .- E[1])) < 1.0e-8
    end

    @testset "spinning start: slides with mu g, then rolls" begin
        m, R, J, mu, w0 = 2.0, 0.2, (0.02, 0.02, 0.04), 0.5, 10.0
        doc = _rr_wheel(; m, R, J, v = 0.0, w = w0, mu, t_end = 0.5, points = 1001)
        cols, res, _ = bg_run(doc)
        @test res.status == "done"
        t = cols["time"]
        tstar = w0 * R / (mu * _RR_G0 * (1 + m * R^2 / J[3]))
        vstar = w0 * R * J[3] / (J[3] + m * R^2)
        # the body frame turns with the wheel, so the travel is read from the world position
        x(tk) = bg_value(cols, "Pose/px", tk)
        for tk in (0.02, 0.05, 0.1)
            @test tk < tstar
            @test isapprox(x(tk), 0.5 * mu * _RR_G0 * tk^2; rtol = 1.0e-4)
        end
        # rolling after t*: the world speed is constant v*
        @test isapprox((x(0.5) - x(0.4)) / 0.1, vstar; rtol = 1.0e-5)
        @test isapprox(bg_value(cols, "Pose/tw[3]", 0.5), vstar / R; atol = 1.0e-4)
        @test abs(bg_value(cols, "Tyre/s_lon", 0.5)) < 1.0e-6
        # sliding: the friction force is mu f_n against the slip
        @test isapprox(abs(bg_value(cols, "Tyre/f_lon", 0.05)), mu * m * _RR_G0; rtol = 1.0e-4)
        lost = 0.5 * J[3] * w0^2 - 0.5 * (m * vstar^2 + J[3] * (vstar / R)^2)
        Pd = _rr_cumint(t, cols["Tyre/Pd"])
        @test isapprox(Pd[end], lost; rtol = 1.0e-4)
        E = _rr_body_energy(cols, m) .+ cols["Tyre/Ec"] .+ Pd
        @test maximum(abs.(E .- E[1])) < 1.0e-4 * lost
    end

    @testset "drilling damping about the vertical" begin
        m, R, J, bsp, wz = 2.0, 0.2, (0.02, 0.02, 0.04), 0.01, 2.0
        # world up is body -y for the upright start pose
        doc = _rr_wheel(; m, R, J, P0 = (0.0, -J[2] * wz, 0.0, 0.0, 0.0, 0.0), bsp, t_end = 1.0, points = 201)
        cols, res, _ = bg_run(doc)
        @test res.status == "done"
        for tk in (0.25, 0.5, 1.0)
            @test isapprox(-bg_value(cols, "Pose/tw[2]", tk), wz * exp(-bsp * tk / J[2]); rtol = 1.0e-6)
        end
        @test maximum(abs, cols["Tyre/camber"]) < 1.0e-6
    end
end
