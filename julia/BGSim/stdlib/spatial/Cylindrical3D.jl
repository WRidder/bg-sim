@block Cylindrical3D begin
    # Spatial cylindrical joint, **fixed structure** (J-MB9 correction, n = 2): rotation `q1`
    # about and translation `q2` along the **local z axis of the joint frame**. D-MB8: one
    # **Rotation** port (`drive1`) and one **Translation** port (`drive2`).
    #
    # The four hard directions are compliant: `dth` (rotations about x/y) and the two
    # perpendicular translations `dl = (dl_x, dl_y)`, all integral (no W201).
    #
    # Exact chart (J-MB9 review): the child pose in the parent frame is
    #
    #     H = (R, q2 ez + Rz(q1) (dl_x, dl_y, 0)),    R = Rz(q1) Rg(dth/2),
    #
    # `Rg(g)` the rotation of the quaternion `(1, g)` (Gibbs vector `g = dth/2`, polynomial over
    # `D = 1 + |g|^2`); `dl` is measured in the nominal child frame `Rz(q1)` (the frame before
    # the deflection rotation), which keeps the chart division-free. Both adjoints use this
    # pose (`V_rel = child.f - Ad(H)^-1 parent.f`, `parent.e = -Ad(H)^-T child.e`), so the
    # deflection lever of the translation rate (the 3-D J-MB7 term) is the `w_p x p` part of
    # `Ad(H)^-1` and exact. The chart rates are the closed-form inverse of the Jacobian:
    #
    #     qdot1 = w_z + g_x w_y - g_y w_x,   dth' = B23 w        (as Revolute3D)
    #     y = Rg v;   qdot2 = y_z,   dl_x' = y_x + dl_y qdot1,   dl_y' = y_y - dl_x qdot1
    #
    # The conjugate wrench is `child.e = B^T [tau1; F; Fx; Fy; tau2]`: the rotational rows
    # see `tau1 + dl_y Fx - dl_x Fy` (the in-plane lever of the perpendicular force about the
    # axis) and the linear rows are `Rg^T (Fx, Fy, tau2)`; `F = kr dth + br dth'`,
    # `Fx,y = kt dl + bt dl'`. On a run
    #
    #     parent.e.parent.f + child.e.child.f + drive1.e*qdot1 + drive2.e*qdot2
    #         = d/dt(1/2 kr|dth|^2 + 1/2 kt|dl|^2) + br|dth'|^2 + bt|dl'|^2
    #
    # holds identically and the pose is exactly the integral of the twists. `pose` is `H` on
    # the D-MB6 chart (quaternion `Rz(q1) (x) (1, g)`, origin `q2 ez + Rz dl`).
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive1::Power{Rotation}
        drive2::Power{Translation}
    end
    @parameters begin
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Stiffness of the two held rotations"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Damping of the two held rotations"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Stiffness of the two perpendicular translations"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Damping of the two perpendicular translations"]
        q10::Real = 0.0, [unit = "rad", description = "Initial rotation"]
        q20::Real = 0.0, [unit = "m", description = "Initial translation"]
    end
    @variables begin
        cq::Real = 1.0, [unit = "1", description = "cos(q1)"]
        sq::Real = 0.0, [unit = "1", description = "sin(q1)"]
        q1::Real = 0.0, [unit = "rad", description = "Rotation about z"]
        q2::Real = 0.0, [unit = "m", description = "Translation along z"]
        qd1::Real = 0.0, [unit = "rad/s", description = "Rotation rate"]
        qd2::Real = 0.0, [unit = "m/s", description = "Translation rate"]
        dth::Vec{2} = [0.0, 0.0], [unit = "rad", state = :prefer, description = "Rotational deflection about x and y (child frame)"]
        dl::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Perpendicular translational deflection (nominal child frame)"]
        gx::Real = 0.0, [unit = "1", description = "Gibbs vector x of the deflection, dth_x/2"]
        gy::Real = 0.0, [unit = "1", description = "Gibbs vector y of the deflection, dth_y/2"]
        D::Real = 1.0, [unit = "1", description = "1 + |g|^2"]
        Rg::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Deflection rotation Rg(g)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Relative rotation Rz(q1) Rg (child to parent)"]
        pr::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Child origin in the parent frame, q2 ez + Rz dl"]
        u::Vec{3} = [0.0, 0.0, 0.0], [description = "parent.f[4:6] + parent.f[1:3] x pr"]
        wn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent angular rate in the child frame"]
        vn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent linear rate at the child origin, in the child frame"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(H)^-1 parent"]
        y::Vec{3} = [0.0, 0.0, 0.0], [description = "Rg V_rel[4:6]: the origin velocity in the nominal child frame"]
        thd::Vec{2} = [0.0, 0.0], [unit = "rad/s", description = "Rotational deflection rate"]
        dld::Vec{2} = [0.0, 0.0], [unit = "m/s", description = "Perpendicular deflection rate"]
        F::Vec{2} = [0.0, 0.0], [unit = "N*m", description = "Held-rotation spring/damper torques"]
        Fp::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "(Fx, Fy, tau2): the force in the nominal child frame"]
        Wl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Rz Fp: the force in the parent frame"]
        ta::Real = 0.0, [unit = "N*m", description = "tau1 + dl_y Fx - dl_x Fy: the axial torque with the in-plane lever"]
        tq::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "B^T [ta; F]: the rotational wrench"]
        tau1::Real = 0.0, [unit = "N*m", description = "Axial torque carried by drive1"]
        tau2::Real = 0.0, [unit = "N", description = "Axial force carried by drive2"]
    end
    @outputs begin
        q1out::Real, [unit = "rad"]
        q2out::Real, [unit = "m"]
        qd1out::Real, [unit = "rad/s"]
        qd2out::Real, [unit = "m/s"]
        pose::Vec{7}
        dang::Vec{2}, [unit = "rad"]
        dlin::Vec{2}, [unit = "m"]
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
        pr[1] ~ cq * dl[1] - sq * dl[2]
        pr[2] ~ sq * dl[1] + cq * dl[2]
        pr[3] ~ q2
        # Ad(H)^-1 [w; v] = [R^T w; R^T (v + w x pr)]
        u[1] ~ parent.f[4] + (parent.f[2] * pr[3] - parent.f[3] * pr[2])
        u[2] ~ parent.f[5] + (parent.f[3] * pr[1] - parent.f[1] * pr[3])
        u[3] ~ parent.f[6] + (parent.f[1] * pr[2] - parent.f[2] * pr[1])
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
        for i in 1:3
            y[i] ~ Rg[i, 1] * Vrel[4] + Rg[i, 2] * Vrel[5] + Rg[i, 3] * Vrel[6]
        end
        qd2 ~ y[3]
        dld[1] ~ y[1] + dl[2] * qd1
        dld[2] ~ y[2] - dl[1] * qd1
        q1 ~ q10 + int(qd1, 0.0)
        q2 ~ q20 + int(qd2, 0.0)
        ddt(dth[1]) ~ thd[1]
        ddt(dth[2]) ~ thd[2]
        ddt(dl[1]) ~ dld[1]
        ddt(dl[2]) ~ dld[2]
        F[1] ~ kr * dth[1] + br * thd[1]
        F[2] ~ kr * dth[2] + br * thd[2]
        Fp[1] ~ kt * dl[1] + bt * dld[1]
        Fp[2] ~ kt * dl[2] + bt * dld[2]
        Fp[3] ~ tau2
        # child.e = B^T [tau1; F; Fp]
        ta ~ tau1 + dl[2] * Fp[1] - dl[1] * Fp[2]
        tq[1] ~ -gy * ta + (1.0 + gx * gx - gy * gy) * F[1] + 2.0 * gx * gy * F[2]
        tq[2] ~ gx * ta + 2.0 * gx * gy * F[1] + (1.0 - gx * gx + gy * gy) * F[2]
        tq[3] ~ ta + 2.0 * gy * F[1] - 2.0 * gx * F[2]
        child.e[1] ~ tq[1]
        child.e[2] ~ tq[2]
        child.e[3] ~ tq[3]
        child.e[4] ~ Rg[1, 1] * Fp[1] + Rg[2, 1] * Fp[2] + Rg[3, 1] * Fp[3]
        child.e[5] ~ Rg[1, 2] * Fp[1] + Rg[2, 2] * Fp[2] + Rg[3, 2] * Fp[3]
        child.e[6] ~ Rg[1, 3] * Fp[1] + Rg[2, 3] * Fp[2] + Rg[3, 3] * Fp[3]
        # parent.e = -Ad(H)^-T child.e = -[R tq + pr x Wl; Wl], Wl = R child.e_lin = Rz Fp
        Wl[1] ~ cq * Fp[1] - sq * Fp[2]
        Wl[2] ~ sq * Fp[1] + cq * Fp[2]
        Wl[3] ~ Fp[3]
        parent.e[1] ~ -(R[1, 1] * tq[1] + R[1, 2] * tq[2] + R[1, 3] * tq[3] + (pr[2] * Wl[3] - pr[3] * Wl[2]))
        parent.e[2] ~ -(R[2, 1] * tq[1] + R[2, 2] * tq[2] + R[2, 3] * tq[3] + (pr[3] * Wl[1] - pr[1] * Wl[3]))
        parent.e[3] ~ -(R[3, 1] * tq[1] + R[3, 2] * tq[2] + R[3, 3] * tq[3] + (pr[1] * Wl[2] - pr[2] * Wl[1]))
        parent.e[4] ~ -Wl[1]
        parent.e[5] ~ -Wl[2]
        parent.e[6] ~ -Wl[3]
        drive1.e ~ -tau1
        drive1.f ~ qd1
        drive2.e ~ -tau2
        drive2.f ~ qd2
        q1out ~ q1
        q2out ~ q2
        qd1out ~ qd1
        qd2out ~ qd2
        pose[1] ~ cos(0.5 * q1)
        pose[2] ~ cos(0.5 * q1) * gx - sin(0.5 * q1) * gy
        pose[3] ~ cos(0.5 * q1) * gy + sin(0.5 * q1) * gx
        pose[4] ~ sin(0.5 * q1)
        pose[5] ~ pr[1]
        pose[6] ~ pr[2]
        pose[7] ~ pr[3]
        dang[1] ~ dth[1]
        dang[2] ~ dth[2]
        dlin[1] ~ dl[1]
        dlin[2] ~ dl[2]
        for k in 1:6
            Vrelout[k] ~ Vrel[k]
        end
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
        drive1 => :flow_out
        drive2 => :flow_out
    end
end
