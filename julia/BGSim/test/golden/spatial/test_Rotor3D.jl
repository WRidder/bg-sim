# Golden tests of `stdlib:spatial/Rotor3D` (the flywheel of the `gyrover` example): a carrier
# body in free space (no gravity, no contact) with a rotor about its z axis.
#
#   1. spin-up: a constant motor torque tau between carrier and rotor gives the rotor
#      h = tau t and the carrier the opposite axial momentum, J3 w_z = -tau t, so the relative
#      rate is w_rel = tau t (1/Ja + 1/J3); the transverse rates stay zero;
#   2. torque-free gyrostat: with an axisymmetric carrier (J1 = J2) and the rotor momentum h,
#      the body-frame transverse rate turns at Omega = ((J3 - J1) w_z + h)/J1:
#      w_x = a cos(Omega t), w_y = a sin(Omega t), w_z constant (this fixes the sign of the
#      gyroscopic torque); the world angular momentum R (J w + h e_z) and the energy
#      w.J w/2 + h^2/(2 Ja) are constant.
using Test
using BGSim
using LinearAlgebra

if !isdefined(@__MODULE__, :_rr_wheel)
    include(joinpath(@__DIR__, "..", "contact", "rolling_rig.jl"))
end

"""A carrier body in free space with a Rotor3D driven by a constant torque `tau`."""
function _rt_model(; J = (0.02, 0.03, 0.05), m = 1.0, Ja = 0.003, h0 = 0.0, w0 = (0.0, 0.0, 0.0),
    tau = 0.0, t_end = 1.0, points = 201)
    d = _rr_d
    nodes = Any[
        bg_node("b", "Carrier", bg_ref("stdlib:spatial/RigidBody3D");
            params = d("m" => string(m), "J" => _rr_vec(J), "g0" => "0.0"),
            starts = d("inertia/P" => _rr_vec((J[1] * w0[1], J[2] * w0[2], J[3] * w0[3], 0.0, 0.0, 0.0)))),
        bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D")),
        bg_node("r", "Rotor", bg_ref("stdlib:spatial/Rotor3D"); params = d("Ja" => string(Ja)),
            starts = d("h" => string(h0))),
        bg_node("se", "Motor", bg_ref("stdlib:bondgraph/Se"); params = d("e" => string(tau))),
    ]
    conns = Any[
        bg_conn("c1", "signal", "b", "V", "pose", "tw"),
        bg_conn("c2", "signal", "pose", "g", "b", "g"),
        bg_conn("c3", "bond", "b", "p", "r", "p"),
        bg_conn("c4", "bond", "se", "p", "r", "drive"),
    ]
    return bg_model("RotorRig", nodes, conns; t_end = t_end, points = points, reltol = 1.0e-10,
        abstol = 1.0e-12)
end

_rt_R(q) = (q = q ./ norm(q); (w, x, y, z) = q;
    [1-2(y^2+z^2) 2(x*y-w*z) 2(x*z+w*y); 2(x*y+w*z) 1-2(x^2+z^2) 2(y*z-w*x); 2(x*z-w*y) 2(y*z+w*x) 1-2(x^2+y^2)])

@testset "Rotor3D (golden)" begin
    @testset "spin-up: reaction on the carrier" begin
        J, Ja, tau = (0.02, 0.03, 0.05), 0.003, 0.1
        cols, res, _ = bg_run(_rt_model(; J, Ja, tau))
        @test res.status == "done"
        for tk in (0.3, 1.0)
            @test isapprox(bg_value(cols, "Rotor/H", tk), tau * tk; rtol = 1.0e-8)
            @test isapprox(bg_value(cols, "Pose/tw[3]", tk), -tau * tk / J[3]; rtol = 1.0e-8)
            @test isapprox(bg_value(cols, "Rotor/w_rel", tk), tau * tk * (1 / Ja + 1 / J[3]); rtol = 1.0e-8)
            @test isapprox(bg_value(cols, "Rotor/w_abs", tk), tau * tk / Ja; rtol = 1.0e-8)
        end
        @test maximum(abs, cols["Pose/tw[1]"]) < 1.0e-12
        @test maximum(abs, cols["Pose/tw[2]"]) < 1.0e-12
    end

    @testset "torque-free gyrostat: nutation rate and invariants" begin
        J, Ja, h, a, wz = (0.02, 0.02, 0.05), 0.003, 0.5, 0.3, 1.0
        cols, res, _ = bg_run(_rt_model(; J, Ja, h0 = h, w0 = (a, 0.0, wz), t_end = 1.0, points = 1001))
        @test res.status == "done"
        Om = ((J[3] - J[1]) * wz + h) / J[1]
        t = cols["time"]
        wx, wy, w3 = cols["Pose/tw[1]"], cols["Pose/tw[2]"], cols["Pose/tw[3]"]
        @test maximum(abs.(wx .- a .* cos.(Om .* t))) < 1.0e-6
        @test maximum(abs.(wy .- a .* sin.(Om .* t))) < 1.0e-6
        @test maximum(abs.(w3 .- wz)) < 1.0e-9
        @test maximum(abs.(cols["Rotor/H"] .- h)) < 1.0e-12
        L0 = nothing
        Lerr = 0.0
        Eerr = 0.0
        E0 = nothing
        for i in eachindex(t)
            q = [cols["Pose/qw"][i], cols["Pose/qx"][i], cols["Pose/qy"][i], cols["Pose/qz"][i]]
            w = [wx[i], wy[i], w3[i]]
            L = _rt_R(q) * (collect(J) .* w .+ [0.0, 0.0, cols["Rotor/H"][i]])
            E = 0.5 * dot(w, collect(J) .* w) + cols["Rotor/Ek"][i]
            L0 === nothing && (L0 = L; E0 = E)
            Lerr = max(Lerr, norm(L - L0))
            Eerr = max(Eerr, abs(E - E0))
        end
        @test Lerr < 1.0e-8
        @test Eerr < 1.0e-8
    end
end
