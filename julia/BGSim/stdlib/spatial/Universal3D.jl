@block Universal3D begin
    # Spatial universal (Cardan) joint, **fixed structure** (J-MB9 correction, n = 2): the first
    # rotation `q1` is about the **local z axis of the joint frame**, the second `q2` about the
    # x axis of the frame already rotated by `q1` (the second axis follows the first rotation).
    # D-MB8: two **Rotation** ports, `drive1` and `drive2`.
    #
    # The hard directions are the rotation about the intermediate y axis (one deflection `dt`,
    # the axis `u = [0, cos q2, -sin q2]` in the child frame) and the three translations `dl`
    # (child frame). All states are integral (no W201).
    #
    # Exact chart (J-MB9 review): the child pose in the parent frame is
    #
    #     H = (R, R dl),    R = Rz(q1) Ry(dt) Rx(q2),
    #
    # a z-y-x chart whose middle angle is the deflection; `dt` is an exact angle (trigonometric,
    # no series). Both adjoints use this pose (`V_rel = child.f - Ad(H)^-1 parent.f`,
    # `parent.e = -Ad(H)^-T child.e`) and the chart rates are the closed-form inverse of the
    # Jacobian: with `c2, s2 = cos q2, sin q2` and `ct, st = cos dt, sin dt`,
    #
    #     qdot1 = (s2 w_y + c2 w_z) / ct,   dt' = c2 w_y - s2 w_z,   qdot2 = w_x + st qdot1,
    #     dl'   = v - w x dl.
    #
    # The division by `cos(dt)` is the inverse of a non-singular chart (it is 1 at zero
    # deflection; no guard, no Gram inverse) and is the only one in the joint. The conjugate
    # wrench is `child.e = B^T [tau1; fd; tau2; Fl]`: with `T = (tau1 + st tau2) / ct`,
    # `child.e_ang = (tau2, s2 T, c2 T) + fd u + Fl x dl`, `child.e_lin = Fl`, `fd = kr dt +
    # br dt'`, `Fl = kt dl + bt dl'`. On a run
    #
    #     parent.e.parent.f + child.e.child.f + drive1.e*qdot1 + drive2.e*qdot2
    #         = d/dt(1/2 kr dt^2 + 1/2 kt|dl|^2) + br dt'^2 + bt|dl'|^2
    #
    # holds identically and the pose is exactly the integral of the twists. `pose` is `H` on
    # the D-MB6 chart (the quaternion `z(q1) (x) y(dt) (x) x(q2)`, origin `R dl`).
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive1::Power{Rotation}
        drive2::Power{Rotation}
    end
    @parameters begin
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Stiffness of the held rotation"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Damping of the held rotation"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Pivot translational stiffness"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Pivot translational damping"]
        q10::Real = 0.0, [unit = "rad", description = "Initial first rotation"]
        q20::Real = 0.0, [unit = "rad", description = "Initial second rotation"]
    end
    @variables begin
        c1::Real = 1.0, [unit = "1", description = "cos(q1)"]
        s1::Real = 0.0, [unit = "1", description = "sin(q1)"]
        c2::Real = 1.0, [unit = "1", description = "cos(q2)"]
        s2::Real = 0.0, [unit = "1", description = "sin(q2)"]
        ct::Real = 1.0, [unit = "1", description = "cos(dt)"]
        st::Real = 0.0, [unit = "1", description = "sin(dt)"]
        q1::Real = 0.0, [unit = "rad", description = "First rotation (about the joint z)"]
        q2::Real = 0.0, [unit = "rad", description = "Second rotation (about the rotated x)"]
        qd1::Real = 0.0, [unit = "rad/s", description = "First rotation rate"]
        qd2::Real = 0.0, [unit = "rad/s", description = "Second rotation rate"]
        dt::Real = 0.0, [unit = "rad", state = :prefer, description = "Rotational deflection about the intermediate y axis, u = [0, cos q2, -sin q2] in the child frame"]
        dl::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Translational deflection (child frame)"]
        M::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Ry(dt) Rx(q2)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Relative rotation Rz(q1) Ry(dt) Rx(q2) (child to parent)"]
        wn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent angular rate in the child frame"]
        vn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent linear rate in the child frame"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(H)^-1 parent"]
        dtd::Real = 0.0, [unit = "rad/s", description = "Deflection rate"]
        dld::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Translational deflection rate"]
        fd::Real = 0.0, [unit = "N*m", description = "Held-rotation spring/damper torque about u"]
        Fl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Pivot spring/damper force (child frame)"]
        T1::Real = 0.0, [unit = "N*m", description = "(tau1 + st tau2) / ct"]
        tq::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "B_rot^T [tau1; fd; tau2]: the rotational wrench without the lever"]
        tau1::Real = 0.0, [unit = "N*m", description = "Torque carried by drive1"]
        tau2::Real = 0.0, [unit = "N*m", description = "Torque carried by drive2"]
    end
    @outputs begin
        q1out::Real, [unit = "rad"]
        q2out::Real, [unit = "rad"]
        qd1out::Real, [unit = "rad/s"]
        qd2out::Real, [unit = "rad/s"]
        pose::Vec{7}
        ddef::Real, [unit = "rad"]
        dlin::Vec{3}, [unit = "m"]
        Vrelout::Vec{6}
    end
    @equations begin
        c1 ~ cos(q1)
        s1 ~ sin(q1)
        c2 ~ cos(q2)
        s2 ~ sin(q2)
        ct ~ cos(dt)
        st ~ sin(dt)
        # M = Ry(dt) Rx(q2), R = Rz(q1) M
        M[1, 1] ~ ct
        M[1, 2] ~ st * s2
        M[1, 3] ~ st * c2
        M[2, 1] ~ 0.0
        M[2, 2] ~ c2
        M[2, 3] ~ -s2
        M[3, 1] ~ -st
        M[3, 2] ~ ct * s2
        M[3, 3] ~ ct * c2
        for j in 1:3
            R[1, j] ~ c1 * M[1, j] - s1 * M[2, j]
            R[2, j] ~ s1 * M[1, j] + c1 * M[2, j]
            R[3, j] ~ M[3, j]
        end
        # Ad(H)^-1 [w; v] = [R^T w; R^T v - dl x R^T w] with H = (R, R dl).
        for i in 1:3
            wn[i] ~ R[1, i] * parent.f[1] + R[2, i] * parent.f[2] + R[3, i] * parent.f[3]
            vn[i] ~ R[1, i] * parent.f[4] + R[2, i] * parent.f[5] + R[3, i] * parent.f[6]
            Vrel[i] ~ child.f[i] - wn[i]
        end
        Vrel[4] ~ child.f[4] - vn[1] - (wn[2] * dl[3] - wn[3] * dl[2])
        Vrel[5] ~ child.f[5] - vn[2] - (wn[3] * dl[1] - wn[1] * dl[3])
        Vrel[6] ~ child.f[6] - vn[3] - (wn[1] * dl[2] - wn[2] * dl[1])
        # xdot = B V_rel
        qd1 ~ (s2 * Vrel[2] + c2 * Vrel[3]) / ct
        dtd ~ c2 * Vrel[2] - s2 * Vrel[3]
        qd2 ~ Vrel[1] + st * qd1
        q1 ~ q10 + int(qd1, 0.0)
        q2 ~ q20 + int(qd2, 0.0)
        ddt(dt) ~ dtd
        dld[1] ~ Vrel[4] - (Vrel[2] * dl[3] - Vrel[3] * dl[2])
        dld[2] ~ Vrel[5] - (Vrel[3] * dl[1] - Vrel[1] * dl[3])
        dld[3] ~ Vrel[6] - (Vrel[1] * dl[2] - Vrel[2] * dl[1])
        ddt(dl[1]) ~ dld[1]
        ddt(dl[2]) ~ dld[2]
        ddt(dl[3]) ~ dld[3]
        fd ~ kr * dt + br * dtd
        Fl[1] ~ kt * dl[1] + bt * dld[1]
        Fl[2] ~ kt * dl[2] + bt * dld[2]
        Fl[3] ~ kt * dl[3] + bt * dld[3]
        # child.e = B^T [tau1; fd; tau2; Fl]
        T1 ~ (tau1 + st * tau2) / ct
        tq[1] ~ tau2
        tq[2] ~ s2 * T1 + c2 * fd
        tq[3] ~ c2 * T1 - s2 * fd
        child.e[1] ~ tq[1] + (Fl[2] * dl[3] - Fl[3] * dl[2])
        child.e[2] ~ tq[2] + (Fl[3] * dl[1] - Fl[1] * dl[3])
        child.e[3] ~ tq[3] + (Fl[1] * dl[2] - Fl[2] * dl[1])
        child.e[4] ~ Fl[1]
        child.e[5] ~ Fl[2]
        child.e[6] ~ Fl[3]
        # parent.e = -Ad(H)^-T child.e = -[R tq; R Fl] (the lever R dl cancels)
        for i in 1:3
            parent.e[i] ~ -(R[i, 1] * tq[1] + R[i, 2] * tq[2] + R[i, 3] * tq[3])
        end
        parent.e[4] ~ -(R[1, 1] * Fl[1] + R[1, 2] * Fl[2] + R[1, 3] * Fl[3])
        parent.e[5] ~ -(R[2, 1] * Fl[1] + R[2, 2] * Fl[2] + R[2, 3] * Fl[3])
        parent.e[6] ~ -(R[3, 1] * Fl[1] + R[3, 2] * Fl[2] + R[3, 3] * Fl[3])
        drive1.e ~ -tau1
        drive1.f ~ qd1
        drive2.e ~ -tau2
        drive2.f ~ qd2
        q1out ~ q1
        q2out ~ q2
        qd1out ~ qd1
        qd2out ~ qd2
        # pose = z(q1) (x) y(dt) (x) x(q2), origin R dl
        pose[1] ~ cos(0.5 * q1) * cos(0.5 * dt) * cos(0.5 * q2) + sin(0.5 * q1) * sin(0.5 * dt) * sin(0.5 * q2)
        pose[2] ~ cos(0.5 * q1) * cos(0.5 * dt) * sin(0.5 * q2) - sin(0.5 * q1) * sin(0.5 * dt) * cos(0.5 * q2)
        pose[3] ~ cos(0.5 * q1) * sin(0.5 * dt) * cos(0.5 * q2) + sin(0.5 * q1) * cos(0.5 * dt) * sin(0.5 * q2)
        pose[4] ~ sin(0.5 * q1) * cos(0.5 * dt) * cos(0.5 * q2) - cos(0.5 * q1) * sin(0.5 * dt) * sin(0.5 * q2)
        pose[5] ~ R[1, 1] * dl[1] + R[1, 2] * dl[2] + R[1, 3] * dl[3]
        pose[6] ~ R[2, 1] * dl[1] + R[2, 2] * dl[2] + R[2, 3] * dl[3]
        pose[7] ~ R[3, 1] * dl[1] + R[3, 2] * dl[2] + R[3, 3] * dl[3]
        ddef ~ dt
        dlin[1] ~ dl[1]
        dlin[2] ~ dl[2]
        dlin[3] ~ dl[3]
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
