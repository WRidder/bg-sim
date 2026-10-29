@block Revolute3D begin
    # Spatial revolute joint, **fixed structure** (J-MB9 correction): exact rotation `q` about
    # the **local z axis of the joint frame**; the user places and orients the joint with
    # `FixedTransform3D`/`FixedTransform3DNeutral` on either side.
    #
    # Joint frame = parent port frame. The five hard directions (`N`: rotations about x/y and
    # the three translations) are compliant. States: the joint coordinate `q`, the rotational
    # deflection `dth = (dth_x, dth_y)` and the translational deflection `dl` (child frame).
    # Every state is integral, so there is no W201.
    #
    # Exact chart (J-MB9 review): the child pose in the parent frame is
    #
    #     H(q, dth, dl) = (R, R dl),    R = Rz(q) Rg(dth/2),
    #
    # where `Rg(g)` is the rotation of the (unnormalised) quaternion `(1, g)`, i.e. the Gibbs
    # vector `g = dth/2 = tan(theta/2) u`: `dth` is the rotation vector to third order, the
    # strain energy is `1/2 kr |dth|^2`, and `Rg`, its kinematics and its inverse are
    # polynomial over `D = 1 + |g|^2` (no series, no guard). Both adjoints use **this** pose:
    #
    #     V_rel    = child.f - Ad(H)^-1 parent.f        (the body twist of H, exactly)
    #     parent.e = -Ad(H)^-T child.e                   (exactly power-continuous)
    #
    # and the chart rates are the closed-form inverse of the chart Jacobian, `xdot = B V_rel`:
    #
    #     qdot   = w_z + g_x w_y - g_y w_x
    #     dth_x' = (1 + g_x^2 - g_y^2) w_x + 2 g_x g_y w_y + 2 g_y w_z
    #     dth_y' = 2 g_x g_y w_x + (1 - g_x^2 + g_y^2) w_y - 2 g_x w_z
    #     dl'    = v - w x dl                              (w, v = V_rel[1:3], V_rel[4:6])
    #
    # (`B` is `A^-1` for `w = A (qdot, dth')`, `A = [Rg^T ez | (I - [g]) e_x / D | (I - [g]) e_y / D]`;
    # no division appears because `(-g_y, g_x, 1) . Rg^T ez = 1`). The transport `w x dl` is
    # `child.f[1:3] x dl` minus the lever already inside `V_rel[4:6]`, i.e. the FIX-MB-5 rule
    # with the absolute child rate. The conjugate wrench is `child.e = B^T [tau; F; Fl]` with
    # `F = kr dth + br dth'`, `Fl = kt dl + bt dl'`, so on a run
    #
    #     parent.e.parent.f + child.e.child.f + drive.e*qdot
    #         = d/dt(1/2 kr|dth|^2 + 1/2 kt|dl|^2) + br|dth'|^2 + bt|dl'|^2 [+ ts*qdot]
    #
    # holds identically, and the pose `H` is exactly the integral of the twists the joint
    # produces, so gravity reading the composed pose closes the energy balance to solver
    # tolerance at every stiffness (the first-order chart leaked O(1/k)).
    #
    # D-MB8: the single drive is a **Rotation** port (N*m, rad/s). `pose` is `H` on the D-MB6
    # chart `(q_w, q_x, q_y, q_z, p)`: the quaternion `Rz(q) (x) (1, g_x, g_y, 0)`, which the
    # consumers normalise, and the origin `R dl`.
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive::Power{Rotation}
    end
    @parameters begin
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Stiffness of the two held rotations"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Damping of the two held rotations"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Pivot translational stiffness"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Pivot translational damping"]
        q0::Real = 0.0, [unit = "rad", description = "Initial joint angle"]

    end
    @variables begin
        cq::Real = 1.0, [unit = "1", description = "cos(q)"]
        sq::Real = 0.0, [unit = "1", description = "sin(q)"]
        q::Real = 0.0, [unit = "rad", description = "Joint angle"]
        qdot::Real = 0.0, [unit = "rad/s", description = "Joint rate"]
        dth::Vec{2} = [0.0, 0.0], [unit = "rad", state = :prefer, description = "Rotational deflection about x and y (child frame)"]
        dl::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Translational deflection (child frame)"]
        gx::Real = 0.0, [unit = "1", description = "Gibbs vector x of the deflection, dth_x/2"]
        gy::Real = 0.0, [unit = "1", description = "Gibbs vector y of the deflection, dth_y/2"]
        D::Real = 1.0, [unit = "1", description = "1 + |g|^2"]
        Rg::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Deflection rotation Rg(g)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Relative rotation Rz(q) Rg (child to parent)"]
        wn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent angular rate in the child frame"]
        vn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent linear rate in the child frame"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(H)^-1 parent"]
        thd::Vec{2} = [0.0, 0.0], [unit = "rad/s", description = "Rotational deflection rate"]
        dld::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Translational deflection rate"]
        F::Vec{2} = [0.0, 0.0], [unit = "N*m", description = "Held-rotation spring/damper torques"]
        Fl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Pivot spring/damper force (child frame)"]
        tq::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "B^T [tau; F]: the rotational wrench without the lever"]
        tau::Real = 0.0, [unit = "N*m", description = "Axial effort carried by the drive"]
    end
    @outputs begin
        qout::Real, [unit = "rad"]
        qdout::Real, [unit = "rad/s"]
        pose::Vec{7}
        dang::Vec{2}, [unit = "rad"]
        dlin::Vec{3}, [unit = "m"]
        Vrelout::Vec{6}
    end
    @equations begin
        cq ~ cos(q)
        sq ~ sin(q)
        gx ~ 0.5 * dth[1]
        gy ~ 0.5 * dth[2]
        D ~ 1.0 + gx * gx + gy * gy
        # Rg = R(1, gx, gy, 0) / D
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
        # Ad(H)^-1 [w; v] = [R^T w; R^T v - dl x R^T w] with H = (R, R dl).
        for i in 1:3
            wn[i] ~ R[1, i] * parent.f[1] + R[2, i] * parent.f[2] + R[3, i] * parent.f[3]
            vn[i] ~ R[1, i] * parent.f[4] + R[2, i] * parent.f[5] + R[3, i] * parent.f[6]
            Vrel[i] ~ child.f[i] - wn[i]
        end
        Vrel[4] ~ child.f[4] - vn[1] - (wn[2] * dl[3] - wn[3] * dl[2])
        Vrel[5] ~ child.f[5] - vn[2] - (wn[3] * dl[1] - wn[1] * dl[3])
        Vrel[6] ~ child.f[6] - vn[3] - (wn[1] * dl[2] - wn[2] * dl[1])
        # xdot = B V_rel (the exact inverse of the chart Jacobian)
        qdot ~ Vrel[3] + gx * Vrel[2] - gy * Vrel[1]
        q ~ q0 + int(qdot, 0.0)
        thd[1] ~ (1.0 + gx * gx - gy * gy) * Vrel[1] + 2.0 * gx * gy * Vrel[2] + 2.0 * gy * Vrel[3]
        thd[2] ~ 2.0 * gx * gy * Vrel[1] + (1.0 - gx * gx + gy * gy) * Vrel[2] - 2.0 * gx * Vrel[3]
        ddt(dth[1]) ~ thd[1]
        ddt(dth[2]) ~ thd[2]
        dld[1] ~ Vrel[4] - (Vrel[2] * dl[3] - Vrel[3] * dl[2])
        dld[2] ~ Vrel[5] - (Vrel[3] * dl[1] - Vrel[1] * dl[3])
        dld[3] ~ Vrel[6] - (Vrel[1] * dl[2] - Vrel[2] * dl[1])
        ddt(dl[1]) ~ dld[1]
        ddt(dl[2]) ~ dld[2]
        ddt(dl[3]) ~ dld[3]
        F[1] ~ kr * dth[1] + br * thd[1]
        F[2] ~ kr * dth[2] + br * thd[2]
        Fl[1] ~ kt * dl[1] + bt * dld[1]
        Fl[2] ~ kt * dl[2] + bt * dld[2]
        Fl[3] ~ kt * dl[3] + bt * dld[3]
        # child.e = B^T [tau; F; Fl]: the angular rows carry the lever Fl x dl of the force
        # acting at the nominal pivot (-dl from the child origin).
        tq[1] ~ -gy * tau + (1.0 + gx * gx - gy * gy) * F[1] + 2.0 * gx * gy * F[2]
        tq[2] ~ gx * tau + 2.0 * gx * gy * F[1] + (1.0 - gx * gx + gy * gy) * F[2]
        tq[3] ~ tau + 2.0 * gy * F[1] - 2.0 * gx * F[2]
        child.e[1] ~ tq[1] + (Fl[2] * dl[3] - Fl[3] * dl[2])
        child.e[2] ~ tq[2] + (Fl[3] * dl[1] - Fl[1] * dl[3])
        child.e[3] ~ tq[3] + (Fl[1] * dl[2] - Fl[2] * dl[1])
        child.e[4] ~ Fl[1]
        child.e[5] ~ Fl[2]
        child.e[6] ~ Fl[3]
        # parent.e = -Ad(H)^-T child.e = -[R (child.e_ang + dl x Fl); R Fl] = -[R tq; R Fl]
        for i in 1:3
            parent.e[i] ~ -(R[i, 1] * tq[1] + R[i, 2] * tq[2] + R[i, 3] * tq[3])
        end
        parent.e[4] ~ -(R[1, 1] * Fl[1] + R[1, 2] * Fl[2] + R[1, 3] * Fl[3])
        parent.e[5] ~ -(R[2, 1] * Fl[1] + R[2, 2] * Fl[2] + R[2, 3] * Fl[3])
        parent.e[6] ~ -(R[3, 1] * Fl[1] + R[3, 2] * Fl[2] + R[3, 3] * Fl[3])
        drive.e ~ -tau
        drive.f ~ qdot
        qout ~ q
        qdout ~ qdot
        # pose = (Rz(q) (x) (1, g), R dl): the chart H itself
        pose[1] ~ cos(0.5 * q)
        pose[2] ~ cos(0.5 * q) * gx - sin(0.5 * q) * gy
        pose[3] ~ cos(0.5 * q) * gy + sin(0.5 * q) * gx
        pose[4] ~ sin(0.5 * q)
        pose[5] ~ R[1, 1] * dl[1] + R[1, 2] * dl[2] + R[1, 3] * dl[3]
        pose[6] ~ R[2, 1] * dl[1] + R[2, 2] * dl[2] + R[2, 3] * dl[3]
        pose[7] ~ R[3, 1] * dl[1] + R[3, 2] * dl[2] + R[3, 3] * dl[3]
        dang[1] ~ dth[1]
        dang[2] ~ dth[2]
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
        drive => :flow_out
    end
end
