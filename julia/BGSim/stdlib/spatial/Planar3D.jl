@block Planar3D begin
    # Spatial planar joint, **fixed structure** (J-MB9 correction, n = 3): rotation `q1` about
    # the **local z axis of the joint frame** and translations `q2`, `q3` along the joint x and y
    # axes (expressed in the parent frame). D-MB8: one **Rotation** (`drive1`) and two
    # **Translation** (`drive2`, `drive3`) ports; the two translation efforts are the parent-frame
    # forces along x and y.
    #
    # Hard directions: the rotations about x and y (`dth`, two states) and the translation along
    # z (`dz`). All integral (no W201).
    #
    # Exact chart (J-MB9 review): the child pose in the parent frame is
    #
    #     H = (R, (q2, q3, dz)),    R = Rz(q1) Rg(dth/2),
    #
    # `Rg(g)` the rotation of the quaternion `(1, g)` (Gibbs vector `g = dth/2`, polynomial over
    # `D = 1 + |g|^2`). Both adjoints use this pose (`V_rel = child.f - Ad(H)^-1 parent.f`,
    # `parent.e = -Ad(H)^-T child.e`), so the deflection lever of the in-plane rates is the
    # `w_p x p` part of `Ad(H)^-1` and exact. The chart rates are the closed-form inverse of
    # the Jacobian:
    #
    #     qdot1 = w_z + g_x w_y - g_y w_x,   dth' = B23 w        (as Revolute3D)
    #     (qdot2, qdot3, dz') = R v                                (parent-frame origin velocity)
    #
    # The conjugate wrench is `child.e = [B_rot^T (tau1, F); R^T (tau2, tau3, fz)]` with
    # `F = kr dth + br dth'`, `fz = kt dz + bt dz'`. On a run
    #
    #     parent.e.parent.f + child.e.child.f + sum drive_k.e*qdot_k
    #         = d/dt(1/2 kr|dth|^2 + 1/2 kt dz^2) + br|dth'|^2 + bt dz'^2
    #
    # holds identically and the pose is exactly the integral of the twists. `pose` is `H` on
    # the D-MB6 chart (quaternion `Rz(q1) (x) (1, g)`, origin `(q2, q3, dz)`).
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive1::Power{Rotation}
        drive2::Power{Translation}
        drive3::Power{Translation}
    end
    @parameters begin
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Stiffness of the two held rotations"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Damping of the two held rotations"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Stiffness of the normal translation"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Damping of the normal translation"]
        q10::Real = 0.0, [unit = "rad", description = "Initial rotation"]
        q20::Real = 0.0, [unit = "m", description = "Initial x translation"]
        q30::Real = 0.0, [unit = "m", description = "Initial y translation"]
    end
    @variables begin
        cq::Real = 1.0, [unit = "1", description = "cos(q1)"]
        sq::Real = 0.0, [unit = "1", description = "sin(q1)"]
        q1::Real = 0.0, [unit = "rad", description = "Rotation about z"]
        q2::Real = 0.0, [unit = "m", description = "Translation along x (parent frame)"]
        q3::Real = 0.0, [unit = "m", description = "Translation along y (parent frame)"]
        qd1::Real = 0.0, [unit = "rad/s", description = "Rotation rate"]
        qd2::Real = 0.0, [unit = "m/s", description = "x translation rate"]
        qd3::Real = 0.0, [unit = "m/s", description = "y translation rate"]
        dth::Vec{2} = [0.0, 0.0], [unit = "rad", state = :prefer, description = "Rotational deflection about x and y (child frame)"]
        dz::Real = 0.0, [unit = "m", state = :prefer, description = "Normal translational deflection (parent frame)"]
        gx::Real = 0.0, [unit = "1", description = "Gibbs vector x of the deflection, dth_x/2"]
        gy::Real = 0.0, [unit = "1", description = "Gibbs vector y of the deflection, dth_y/2"]
        D::Real = 1.0, [unit = "1", description = "1 + |g|^2"]
        Rg::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Deflection rotation Rg(g)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Relative rotation Rz(q1) Rg (child to parent)"]
        u::Vec{3} = [0.0, 0.0, 0.0], [description = "parent.f[4:6] + parent.f[1:3] x (q2, q3, dz)"]
        wn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent angular rate in the child frame"]
        vn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent linear rate at the child origin, in the child frame"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(H)^-1 parent"]
        thd::Vec{2} = [0.0, 0.0], [unit = "rad/s", description = "Rotational deflection rate"]
        dzd::Real = 0.0, [unit = "m/s", description = "Normal deflection rate"]
        F::Vec{2} = [0.0, 0.0], [unit = "N*m", description = "Held-rotation spring/damper torques"]
        Fp::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "(tau2, tau3, fz): the parent-frame force"]
        tq::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "B_rot^T [tau1; F]: the rotational wrench"]
        tau1::Real = 0.0, [unit = "N*m", description = "Torque carried by drive1"]
        tau2::Real = 0.0, [unit = "N", description = "Force along the parent x carried by drive2"]
        tau3::Real = 0.0, [unit = "N", description = "Force along the parent y carried by drive3"]
        fz::Real = 0.0, [unit = "N", description = "Normal spring/damper force"]
    end
    @outputs begin
        q1out::Real, [unit = "rad"]
        q2out::Real, [unit = "m"]
        q3out::Real, [unit = "m"]
        qd1out::Real, [unit = "rad/s"]
        qd2out::Real, [unit = "m/s"]
        qd3out::Real, [unit = "m/s"]
        pose::Vec{7}
        dang::Vec{2}, [unit = "rad"]
        dzout::Real, [unit = "m"]
        Vrelout::Vec{6}
    end
    @equations begin
        cq ~ cos(q1)
        sq ~ sin(q1)
        gx ~ 0.5 * dth[1]
        gy ~ 0.5 * dth[2]
        D ~ 1.0 + gx * gx + gy * gy
        Rg[1, 1] ~ (1.0 + gx * gx - gy * gy) / D
        Rg[1, 2] ~ 2.0 * gx * gy / D
        Rg[1, 3] ~ 2.0 * gy / D
        Rg[2, 1] ~ 2.0 * gx * gy / D
        Rg[2, 2] ~ (1.0 - gx * gx + gy * gy) / D
        Rg[2, 3] ~ -2.0 * gx / D
        Rg[3, 1] ~ -2.0 * gy / D
        Rg[3, 2] ~ 2.0 * gx / D
        Rg[3, 3] ~ (1.0 - gx * gx - gy * gy) / D
        for j in 1:3
            R[1, j] ~ cq * Rg[1, j] - sq * Rg[2, j]
            R[2, j] ~ sq * Rg[1, j] + cq * Rg[2, j]
            R[3, j] ~ Rg[3, j]
        end
        # Ad(H)^-1 [w; v] = [R^T w; R^T (v + w x p)], p = (q2, q3, dz)
        u[1] ~ parent.f[4] + (parent.f[2] * dz - parent.f[3] * q3)
        u[2] ~ parent.f[5] + (parent.f[3] * q2 - parent.f[1] * dz)
        u[3] ~ parent.f[6] + (parent.f[1] * q3 - parent.f[2] * q2)
        for i in 1:3
            wn[i] ~ R[1, i] * parent.f[1] + R[2, i] * parent.f[2] + R[3, i] * parent.f[3]
            vn[i] ~ R[1, i] * u[1] + R[2, i] * u[2] + R[3, i] * u[3]
            Vrel[i] ~ child.f[i] - wn[i]
        end
        Vrel[4] ~ child.f[4] - vn[1]
        Vrel[5] ~ child.f[5] - vn[2]
        Vrel[6] ~ child.f[6] - vn[3]
        # xdot = B V_rel
        qd1 ~ Vrel[3] + gx * Vrel[2] - gy * Vrel[1]
        thd[1] ~ (1.0 + gx * gx - gy * gy) * Vrel[1] + 2.0 * gx * gy * Vrel[2] + 2.0 * gy * Vrel[3]
        thd[2] ~ 2.0 * gx * gy * Vrel[1] + (1.0 - gx * gx + gy * gy) * Vrel[2] - 2.0 * gx * Vrel[3]
        qd2 ~ R[1, 1] * Vrel[4] + R[1, 2] * Vrel[5] + R[1, 3] * Vrel[6]
        qd3 ~ R[2, 1] * Vrel[4] + R[2, 2] * Vrel[5] + R[2, 3] * Vrel[6]
        dzd ~ R[3, 1] * Vrel[4] + R[3, 2] * Vrel[5] + R[3, 3] * Vrel[6]
        q1 ~ q10 + int(qd1, 0.0)
        q2 ~ q20 + int(qd2, 0.0)
        q3 ~ q30 + int(qd3, 0.0)
        ddt(dth[1]) ~ thd[1]
        ddt(dth[2]) ~ thd[2]
        ddt(dz) ~ dzd
        F[1] ~ kr * dth[1] + br * thd[1]
        F[2] ~ kr * dth[2] + br * thd[2]
        fz ~ kt * dz + bt * dzd
        tau2 ~ -drive2.e
        tau3 ~ -drive3.e
        Fp[1] ~ tau2
        Fp[2] ~ tau3
        Fp[3] ~ fz
        # child.e = [B_rot^T (tau1, F); R^T Fp]
        tq[1] ~ -gy * tau1 + (1.0 + gx * gx - gy * gy) * F[1] + 2.0 * gx * gy * F[2]
        tq[2] ~ gx * tau1 + 2.0 * gx * gy * F[1] + (1.0 - gx * gx + gy * gy) * F[2]
        tq[3] ~ tau1 + 2.0 * gy * F[1] - 2.0 * gx * F[2]
        child.e[1] ~ tq[1]
        child.e[2] ~ tq[2]
        child.e[3] ~ tq[3]
        child.e[4] ~ R[1, 1] * Fp[1] + R[2, 1] * Fp[2] + R[3, 1] * Fp[3]
        child.e[5] ~ R[1, 2] * Fp[1] + R[2, 2] * Fp[2] + R[3, 2] * Fp[3]
        child.e[6] ~ R[1, 3] * Fp[1] + R[2, 3] * Fp[2] + R[3, 3] * Fp[3]
        # parent.e = -Ad(H)^-T child.e = -[R tq + p x Fp; Fp], p = (q2, q3, dz)
        parent.e[1] ~ -(R[1, 1] * tq[1] + R[1, 2] * tq[2] + R[1, 3] * tq[3] + (q3 * fz - dz * tau3))
        parent.e[2] ~ -(R[2, 1] * tq[1] + R[2, 2] * tq[2] + R[2, 3] * tq[3] + (dz * tau2 - q2 * fz))
        parent.e[3] ~ -(R[3, 1] * tq[1] + R[3, 2] * tq[2] + R[3, 3] * tq[3] + (q2 * tau3 - q3 * tau2))
        parent.e[4] ~ -tau2
        parent.e[5] ~ -tau3
        parent.e[6] ~ -fz
        drive1.e ~ -tau1
        drive1.f ~ qd1
        drive2.f ~ qd2
        drive3.f ~ qd3
        q1out ~ q1
        q2out ~ q2
        q3out ~ q3
        qd1out ~ qd1
        qd2out ~ qd2
        qd3out ~ qd3
        pose[1] ~ cos(0.5 * q1)
        pose[2] ~ cos(0.5 * q1) * gx - sin(0.5 * q1) * gy
        pose[3] ~ cos(0.5 * q1) * gy + sin(0.5 * q1) * gx
        pose[4] ~ sin(0.5 * q1)
        pose[5] ~ q2
        pose[6] ~ q3
        pose[7] ~ dz
        dang[1] ~ dth[1]
        dang[2] ~ dth[2]
        dzout ~ dz
        for k in 1:6
            Vrelout[k] ~ Vrel[k]
        end
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
        drive1 => :flow_out
        drive2 => :flow_out
        drive3 => :flow_out
    end
end
