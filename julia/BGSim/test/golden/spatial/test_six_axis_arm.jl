# Work package J-MB10: the six-axis arm (plan 6, row J-MB10; Gate C, plan 9).
#
# A UR5-like six-axis serial arm built from the J-MB9 composites (`Revolute3D` joints oriented
# and placed by `FixedTransform3DNeutral`, `RigidBody3D` links with principal-axis inertia,
# gravity on, fixed-base link poses composed algebraically with `LocalPose3D`/`ComposePose3D`),
# run through the real pipeline (`IR.parse_model` -> `Compile.flatten` -> `simulate`, Rodas5P,
# reltol 1e-9, abstol 1e-11) and checked against an **independent** iterative Newton-Euler
# written in `jmb10_arm.jl` (3-vectors and rotation matrices, plain Julia, no stdlib block).
#
#   - inverse dynamics from the model, validated on a smooth multi-frequency trajectory and
#     swept over the stiffness (error falls one decade per decade);
#   - forward dynamics (free swing) against an RK4 of `M(q) qdd = tau - h(q, qd)`;
#   - gravity compensation (the Newton-Euler gravity torques hold the pose);
#   - energy of the free swing, absence of W201, state count, step count and step time (Gate C).
#
# The joints take the drive **effort** and give the flow, so a flow source cannot impose the
# motion (derivative causality, W201); the trajectory is imposed by a stiff tracking servo
# instead, see `_ja_servo` in `jmb10_arm.jl`.
using Test
using BGSim
using LinearAlgebra

if !isdefined(@__MODULE__, :_ja_arm_model)
    include(joinpath(@__DIR__, "jmb10_arm.jl"))
end

# The trajectory of the inverse-dynamics runs: `q_i(t) = q0_i + A_i/w_i (1 - cos(w_i t))`, a
# different frequency per joint so every coupling term is active.
const _JA_Q0 = [0.3, -0.9, 1.1, -0.4, 0.7, 0.2]
const _JA_AMP = [0.8, 0.6, 0.7, 1.0, 0.9, 1.2]
const _JA_FRQ = [2.1, 3.3, 2.7, 4.1, 3.7, 5.3]
# The hold pose of the forward-dynamics and gravity-compensation runs: the arm hangs on the stable
# side (positive-semidefinite potential Hessian, only the vertical joint 1 and the on-axis joint 6
# neutral), so the O(1/k) differences are not amplified by an unstable equilibrium.
const _JA_QH = [0.4, 1.2, -0.6, -0.5, 0.8, 0.3]
_ja_qref(t) = _JA_Q0 .+ _JA_AMP ./ _JA_FRQ .* (1 .- cos.(_JA_FRQ .* t))
_ja_qdref(t) = _JA_AMP .* sin.(_JA_FRQ .* t)
_ja_qddref(t) = _JA_AMP .* _JA_FRQ .* cos.(_JA_FRQ .* t)

"""Joint-space servo gains: `kp = kk`, rate gain at 0.7 of critical for the diagonal inertia."""
function _ja_gains(arm, q, kk)
    M, _ = _ja_mh(arm, q, zeros(length(arm)))
    return kk, [1.4 * sqrt(kk * M[i, i]) for i in eachindex(arm)]
end

"""Inverse dynamics through the model: the servo imposes the trajectory, the model's applied
joint torque (`D_i/p.e`) is compared with the Newton-Euler torque of the reference trajectory.
Returns the per-joint maximum error over the output grid."""
function _ja_inverse(arm, kk; t_end, points)
    kp, kd = _ja_gains(arm, _ja_qref(0.0), kk)
    drives = [_ja_servo(_JA_Q0[i], _JA_AMP[i], _JA_FRQ[i], kp, kd[i]) for i in 1:6]
    # start on the stiff steady state of the servo (e = tau_RNE / kp) so only O(1/kp) is excited
    tau0 = _ja_rne(arm, _ja_qref(0.0), _ja_qdref(0.0), _ja_qddref(0.0))[1]
    doc = _ja_arm_model(arm, drives; kk = kk, q0 = _JA_Q0 .- tau0 ./ kp, qdd0 = _ja_qddref(0.0),
        t_end = t_end, points = points)
    c, r, flat, wall = _ja_run(doc)
    err = zeros(6)
    peak = 0.0
    for (i, t) in enumerate(c["time"])
        tau = _ja_rne(arm, _ja_qref(t), _ja_qdref(t), _ja_qddref(t))[1]
        for j in 1:6
            err[j] = max(err[j], abs(c["D$j/p.e"][i] - tau[j]))
        end
        peak = max(peak, maximum(abs.(tau)))
    end
    return err, peak, c, r, flat, wall
end

"""Total mechanical energy of an arm run: kinetic (from the body momenta), potential (the actual
body origins of the composed poses, so the deflections are included) and the joint strain."""
function _ja_model_energy(arm, c, kk)
    E = zeros(length(c["time"]))
    for i in 1:6
        L = arm[i]
        for k in 1:3
            E .+= 0.5 .* c["B$i/inertia/P[$k]"] .^ 2 ./ L.J[k]
        end
        for k in 4:6
            E .+= 0.5 .* c["B$i/inertia/P[$k]"] .^ 2 ./ L.m
        end
        E .+= _JA_G * L.m .* c["P$i/g[7]"]
        E .+= 0.5 * kk .* (c["J$i/dang[1]"] .^ 2 .+ c["J$i/dang[2]"] .^ 2 .+ c["J$i/dlin[1]"] .^ 2 .+
                           c["J$i/dlin[2]"] .^ 2 .+ c["J$i/dlin[3]"] .^ 2)
    end
    return E
end

"""Heat dissipated so far by the damping of the held directions, `int sum_i br|thd|^2 + bt|dld|^2 dt`
(trapezoid on the output grid), from the joints' recorded deflection rates."""
function _ja_dissipated(arm, c, kk; zeta = 0.7)
    br, bt = _ja_damping(arm, kk, zeta)
    p = zeros(length(c["time"]))
    for i in 1:6
        p .+= br[i] .* (c["J$i/thd[1]"] .^ 2 .+ c["J$i/thd[2]"] .^ 2)
        p .+= bt[i] .* (c["J$i/dld[1]"] .^ 2 .+ c["J$i/dld[2]"] .^ 2 .+ c["J$i/dld[3]"] .^ 2)
    end
    t = c["time"]
    return vcat(0.0, cumsum(0.5 .* (p[1:(end - 1)] .+ p[2:end]) .* diff(t)))
end

"""Forward dynamics rig: open-loop joint torques `offset_i + amp_i sin(w_i t)`, the arm released at
rest at `q0`; returns the run and the Newton-Euler/RK4 reference sampled on the same grid."""
function _ja_forward(arm, kk, q0, offset, amp, frq; t_end, points, dt = 2.0e-4)
    drives = [_ja_effort(offset[i], amp[i], frq[i]) for i in 1:6]
    tau = t -> offset .+ amp .* sin.(frq .* t)
    qdd0 = _ja_fd(arm, q0, zeros(6), tau(0.0))
    doc = _ja_arm_model(arm, drives; kk = kk, q0 = q0, qdd0 = qdd0, t_end = t_end, points = points)
    c, r, flat, wall = _ja_run(doc)
    stride = round(Int, (t_end / (points - 1)) / dt)
    ref = _ja_rk4(arm, tau, q0, zeros(6), dt, stride, t_end)
    @test length(ref) == points
    return c, r, flat, wall, ref
end

@testset "J-MB10 six-axis arm" begin
    arm = _ja_arm()

    # ---------------------------------------------------------------------------------
    # The reference itself: Newton-Euler power balance, symmetric positive mass matrix and the
    # gravity torque as the gradient of the potential
    # ---------------------------------------------------------------------------------
    @testset "independent Newton-Euler reference: power balance, mass matrix, gravity gradient" begin
        for t in (0.11, 0.37, 0.83)
            q, qd, qdd = _ja_qref(t), _ja_qdref(t), _ja_qddref(t)
            tau, _ = _ja_rne(arm, q, qd, qdd)
            h = 1.0e-5
            E(s) = sum(_ja_energy(arm, _ja_qref(s), _ja_qdref(s)))
            dE = (E(t + h) - E(t - h)) / (2h)
            @test isapprox(dot(tau, qd), dE; rtol = 1.0e-8)
        end
        q = _ja_qref(0.5)
        M, h0 = _ja_mh(arm, q, zeros(6))
        @test norm(M - M') <= 1.0e-12 * norm(M)
        @test minimum(eigvals(Symmetric(M))) > 0
        g = zeros(6)
        for j in 1:6
            e = zeros(6)
            e[j] = 1.0e-6
            g[j] = (_ja_energy(arm, q + e, zeros(6))[2] - _ja_energy(arm, q - e, zeros(6))[2]) / 2.0e-6
        end
        @test norm(g - h0) <= 1.0e-6 * norm(h0)
    end

    # ---------------------------------------------------------------------------------
    # Inverse dynamics from the model, swept over the stiffness
    # ---------------------------------------------------------------------------------
    @testset "inverse dynamics from the model vs Newton-Euler, stiffness sweep" begin
        ks = (1.0e7, 1.0e8)
        rel = Float64[]
        for kk in ks
            err, peak, c, r, flat, wall = _ja_inverse(arm, kk; t_end = 0.5, points = 51)
            e = maximum(err) / peak
            push!(rel, e)
            st = _ja_stats(r, flat, 0.5)
            # the whole torque history lies within `1.2e-4 * (1e6 / k)` of the peak joint torque:
            # the servo, the held directions and the pose chart all contribute O(1/k)
            @test e <= 1.2e-4 * (1.0e6 / kk)
            println("J-MB10 inverse dynamics kt=kr=kp=", kk, ": peak torque ", peak, " N m, max error per joint ",
                err, ", relative ", e, "; states ", st.states, ", steps ", st.steps, ", solve ",
                round(st.sim_per_s; digits = 2), " s per simulated s, compile ", round(st.compile_s; digits = 1),
                " s, wall ", round(wall; digits = 1), " s")
        end
        ratios = rel[1:(end - 1)] ./ rel[2:end]
        println("J-MB10 inverse dynamics error ratios per decade: ", ratios)
        @test all(r -> 7.0 <= r <= 13.0, ratios)
    end


    # ---------------------------------------------------------------------------------
    # Forward dynamics with applied torques, against RK4 of M(q) qdd = tau - h(q, qd)
    # ---------------------------------------------------------------------------------
    @testset "forward dynamics: gravity-held pose plus sinusoidal torques vs RK4, stiffness sweep" begin
        q0 = _JA_QH
        offset = _ja_rne(arm, q0, zeros(6), zeros(6))[1]
        amp = 0.35 .* abs.(offset) .+ [4.0, 4.0, 2.0, 0.4, 0.4, 0.05]
        frq = [3.1, 2.3, 4.3, 5.9, 4.7, 6.7]
        t_end, points = 0.5, 51
        errs = Float64[]
        for kk in (1.0e7, 1.0e8)
            c, r, flat, wall, ref = _ja_forward(arm, kk, q0, offset, amp, frq; t_end = t_end, points = points)
            if kk == 1.0e7
                # the reference itself is converged (RK4 at half the step)
                tau = t -> offset .+ amp .* sin.(frq .* t)
                fine = _ja_rk4(arm, tau, q0, zeros(6), 1.0e-4, 2 * round(Int, (t_end / (points - 1)) / 2.0e-4), t_end)
                @test maximum(maximum(abs.(ref[k] .- fine[k])) for k in eachindex(ref)) <= 1.0e-7
                # and the arm really moves
                @test maximum(maximum(abs.(getindex.(ref, j) .- q0[j])) for j in 1:6) > 0.1
            end
            ej = [maximum(abs.(c["J$j/qout"][k] - ref[k][j]) for k in eachindex(ref)) for j in 1:6]
            ev = maximum(maximum(abs.(c["J$j/qdout"][k] - ref[k][6 + j])) for j in 1:6, k in eachindex(ref))
            e = maximum(ej)
            push!(errs, e)
            st = _ja_stats(r, flat, t_end)
            # the angle error is O(1/k): the held directions are compliant, so the model differs
            # from the rigid Newton-Euler by the deflection; `e * k` is bounded by 5e4 N m
            @test e * kk <= 5.0e4
            println("J-MB10 forward dynamics kt=kr=", kk, ": max joint angle error per joint ", ej,
                " rad, rate error ", ev, " rad/s; states ", st.states, ", steps ", st.steps, ", solve ",
                round(st.sim_per_s; digits = 2), " s per simulated s")
        end
        ratios = errs[1:(end - 1)] ./ errs[2:end]
        println("J-MB10 forward dynamics error ratios per decade: ", ratios)
        @test all(r -> r >= 8.0, ratios)
    end

    # ---------------------------------------------------------------------------------
    # Free swing: energy balance, forward dynamics, W201 and the Gate C numbers
    # ---------------------------------------------------------------------------------
    @testset "free swing: energy balance, forward dynamics, state and step counts" begin
        q0 = _JA_QH
        zero6 = zeros(6)
        t_end, points = 1.0, 101
        kk = 1.0e7
        c, r, flat, wall, ref = _ja_forward(arm, kk, q0, zero6, zero6, ones(6); t_end = t_end,
            points = points, dt = 4.0e-4)
        E = _ja_model_energy(arm, c, kk)
        heat = _ja_dissipated(arm, c, kk)
        Eref = [sum(_ja_energy(arm, y[1:6], y[7:12])) for y in ref]
        pes = [_ja_energy(arm, y[1:6], y[7:12])[2] for y in ref]
        swing = maximum(pes) - minimum(pes)
        @test swing > 1.0                                         # a real swing (J)
        # the rigid reference conserves its own energy (it validates the RNE/RK4 pair)
        @test maximum(abs.(Eref .- Eref[1])) / swing <= 1.0e-8
        # the model loses exactly the heat of the damping of the held directions: KE + PE + strain
        # falls by it (raw drift), and the balance with the heat closes
        raw = maximum(abs.(E .- E[1])) / swing
        balance = maximum(abs.((E .+ heat) .- E[1])) / swing
        @test heat[end] > 0
        @test balance <= 2.0e-6
        e = maximum(maximum(abs.(c["J$j/qout"][k] - ref[k][j])) for j in 1:6, k in eachindex(ref))
        @test e * kk <= 4.0e5
        st = _ja_stats(r, flat, t_end)
        println("J-MB10 free swing (", t_end, " s, kt=kr=", kk, "): energy drift ", raw, " of the ", swing,
            " J swing, with the dissipated heat ", balance, " (heat ", heat[end], " J), max joint angle error ",
            e, " rad; states ", st.states, ", steps ", st.steps, ", solve ", round(st.sim_per_s; digits = 2),
            " s per simulated s, wall ", round(wall; digits = 1), " s")
    end

    # ---------------------------------------------------------------------------------
    # Gravity compensation: the Newton-Euler gravity torques hold the pose
    # ---------------------------------------------------------------------------------
    @testset "gravity compensation: drive torques = RNE gravity torques hold the pose" begin
        q0 = _JA_QH
        tau_g = _ja_rne(arm, q0, zeros(6), zeros(6))[1]
        @test maximum(abs.(tau_g)) > 20.0                           # the pose really loads the joints
        t_end, points = 1.0, 21
        drifts = Float64[]
        for kk in (1.0e7, 1.0e8)
            doc = _ja_arm_model(arm, [_ja_effort(tau_g[i], 0.0, 1.0) for i in 1:6]; kk = kk, q0 = q0,
                t_end = t_end, points = points)
            c, r, flat, wall = _ja_run(doc)
            d = maximum(maximum(abs.(c["J$j/qout"] .- q0[j])) for j in 1:6)
            v = maximum(maximum(abs.(c["J$j/qdout"])) for j in 1:6)
            push!(drifts, d)
            # the compliant directions leave an O(1/k) torque imbalance (the deflected links sit
            # slightly off the rigid pose) that the light, neutral joints integrate twice
            @test d * kk <= 7.0e3
            println("J-MB10 gravity compensation kt=kr=", kk, " over ", t_end, " s: max joint drift ", d,
                " rad, max joint rate ", v, " rad/s")
        end
        println("J-MB10 gravity compensation drift ratio per decade: ", drifts[1] / drifts[2])
        @test drifts[1] / drifts[2] >= 8.0
        # without the compensation the same pose falls (so the hold above is not vacuous)
        doc = _ja_arm_model(arm, [_ja_effort(0.0, 0.0, 1.0) for i in 1:6]; kk = 1.0e7, q0 = q0,
            qdd0 = _ja_fd(arm, q0, zeros(6), zeros(6)), t_end = 0.5, points = 11)
        c, r, flat, wall = _ja_run(doc)
        @test maximum(maximum(abs.(c["J$j/qout"] .- q0[j])) for j in 1:6) > 0.1
    end
end
