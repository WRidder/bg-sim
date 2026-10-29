@block Prismatic3D begin
    # Spatial prismatic joint, **fixed structure** (J-MB9 correction): exact translation `q`
    # along the **local z axis of the joint frame** (place the joint with `FixedTransform3D`).
    #
    #
    # The five hard directions are compliant: the **whole rotation** (`dth`, three components)
    # and the two translations perpendicular to the axis (`dl = (dl_x, dl_y)`, the z component
    # is the free coordinate). All states are integral (no W201).
    #
    # Exact chart (J-MB9 review): the child pose in the parent frame is
    #
    #     H(q, dth, dl) = (Rg(dth/2), (dl_x, dl_y, q)),
    #
    # with `Rg(g)` the rotation of the quaternion `(1, g)` (Gibbs vector `g = dth/2`, so `dth`
    # is the rotation vector to third order and the strain energy is `1/2 kr |dth|^2`); the
    # translations are parent-frame coordinates, which is what makes the chart division-free.
    # Both adjoints use this pose:
    #
    #     V_rel    = child.f - Ad(H)^-1 parent.f        (the body twist of H, exactly)
    #     parent.e = -Ad(H)^-T child.e                   (exactly power-continuous)
    #
    # and the chart rates are the closed-form inverse of the chart Jacobian:
    #
    #     dth' = w + g x w + g (g . w)                   (the Gibbs kinematics, 2 g' = ...)
    #     (dl_x', dl_y', qdot) = Rg v                     (w, v = V_rel[1:3], V_rel[4:6])
    #
    # The deflection lever of the J-MB7 term (`qdot = n . V_rel - n . (w_p x dl)`) is the
    # `w_p x p` part of `Ad(H)^-1` and is therefore exact. The conjugate wrench is
    # `child.e = [(I - [g] + g g^T) F; Rg^T (Fx, Fy, tau)]` with `F = kr dth + br dth'`,
    # `Fx,y = kt dl + bt dl'`, so on a run
    #
    #     parent.e.parent.f + child.e.child.f + drive.e*qdot
    #         = d/dt(1/2 kr|dth|^2 + 1/2 kt|dl|^2) + br|dth'|^2 + bt|dl'|^2 [+ ts*qdot]
    #
    # holds identically and the pose is exactly the integral of the twists, so the energy of a
    # chain closes to solver tolerance at every stiffness (the first-order chart leaked O(1/k)).
    #
    # D-MB8: the drive is a **Translation** port (N, m/s). `pose` is `H` on the D-MB6 chart:
    # the quaternion `(1, g)` (the consumers normalise) and the origin `(dl_x, dl_y, q)`.
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive::Power{Translation}
    end
    @parameters begin
        kr::Real = 1.0e6, [unit = "N*m/rad", min = 0, description = "Stiffness of the held rotations"]
        br::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Damping of the held rotations"]
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Stiffness of the two perpendicular translations"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Damping of the two perpendicular translations"]
        q0::Real = 0.0, [unit = "m", description = "Initial joint displacement"]

    end
    @variables begin
        q::Real = 0.0, [unit = "m", description = "Joint displacement along the axis"]
        qdot::Real = 0.0, [unit = "m/s", description = "Joint rate"]
        dth::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad", state = :prefer, description = "Rotational deflection (child frame)"]
        dl::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Perpendicular translational deflection (parent frame)"]
        g::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "Gibbs vector of the deflection, dth/2"]
        D::Real = 1.0, [unit = "1", description = "1 + |g|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Deflection rotation Rg(g) (child to parent)"]
        u::Vec{3} = [0.0, 0.0, 0.0], [description = "parent.f[4:6] + parent.f[1:3] x p"]
        wn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent angular rate in the child frame"]
        vn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent linear rate at the child origin, in the child frame"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(H)^-1 parent"]
        gw::Real = 0.0, [description = "g . V_rel[1:3]"]
        thd::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Rotational deflection rate"]
        dld::Vec{2} = [0.0, 0.0], [unit = "m/s", description = "Perpendicular deflection rate"]
        F::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Held-rotation spring/damper torques"]
        Fp::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "(Fx, Fy, tau): the parent-frame force"]
        gF::Real = 0.0, [unit = "N*m", description = "g . F"]
        tau::Real = 0.0, [unit = "N", description = "Axial force carried by the drive"]
    end
    @outputs begin
        qout::Real, [unit = "m"]
        qdout::Real, [unit = "m/s"]
        pose::Vec{7}
        dang::Vec{3}, [unit = "rad"]
        dlin::Vec{2}, [unit = "m"]
        Vrelout::Vec{6}
    end
    @equations begin
        for k in 1:3
            g[k] ~ 0.5 * dth[k]
        end
        D ~ 1.0 + g[1] * g[1] + g[2] * g[2] + g[3] * g[3]
        # R = R(1, g) / D
        R[1, 1] ~ (1.0 + g[1] * g[1] - g[2] * g[2] - g[3] * g[3]) / D
        R[1, 2] ~ 2.0 * (g[1] * g[2] - g[3]) / D
        R[1, 3] ~ 2.0 * (g[1] * g[3] + g[2]) / D
        R[2, 1] ~ 2.0 * (g[1] * g[2] + g[3]) / D
        R[2, 2] ~ (1.0 - g[1] * g[1] + g[2] * g[2] - g[3] * g[3]) / D
        R[2, 3] ~ 2.0 * (g[2] * g[3] - g[1]) / D
        R[3, 1] ~ 2.0 * (g[1] * g[3] - g[2]) / D
        R[3, 2] ~ 2.0 * (g[2] * g[3] + g[1]) / D
        R[3, 3] ~ (1.0 - g[1] * g[1] - g[2] * g[2] + g[3] * g[3]) / D
        # Ad(H)^-1 [w; v] = [R^T w; R^T (v + w x p)] with p = (dl_x, dl_y, q).
        u[1] ~ parent.f[4] + (parent.f[2] * q - parent.f[3] * dl[2])
        u[2] ~ parent.f[5] + (parent.f[3] * dl[1] - parent.f[1] * q)
        u[3] ~ parent.f[6] + (parent.f[1] * dl[2] - parent.f[2] * dl[1])
        for i in 1:3
            wn[i] ~ R[1, i] * parent.f[1] + R[2, i] * parent.f[2] + R[3, i] * parent.f[3]
            vn[i] ~ R[1, i] * u[1] + R[2, i] * u[2] + R[3, i] * u[3]
            Vrel[i] ~ child.f[i] - wn[i]
        end
        Vrel[4] ~ child.f[4] - vn[1]
        Vrel[5] ~ child.f[5] - vn[2]
        Vrel[6] ~ child.f[6] - vn[3]
        # xdot = B V_rel: Gibbs kinematics for the rotation, (dl', qdot) = R v for the translation
        gw ~ g[1] * Vrel[1] + g[2] * Vrel[2] + g[3] * Vrel[3]
        thd[1] ~ Vrel[1] + (g[2] * Vrel[3] - g[3] * Vrel[2]) + g[1] * gw
        thd[2] ~ Vrel[2] + (g[3] * Vrel[1] - g[1] * Vrel[3]) + g[2] * gw
        thd[3] ~ Vrel[3] + (g[1] * Vrel[2] - g[2] * Vrel[1]) + g[3] * gw
        for k in 1:3
            ddt(dth[k]) ~ thd[k]
        end
        dld[1] ~ R[1, 1] * Vrel[4] + R[1, 2] * Vrel[5] + R[1, 3] * Vrel[6]
        dld[2] ~ R[2, 1] * Vrel[4] + R[2, 2] * Vrel[5] + R[2, 3] * Vrel[6]
        qdot ~ R[3, 1] * Vrel[4] + R[3, 2] * Vrel[5] + R[3, 3] * Vrel[6]
        ddt(dl[1]) ~ dld[1]
        ddt(dl[2]) ~ dld[2]
        q ~ q0 + int(qdot, 0.0)
        for k in 1:3
            F[k] ~ kr * dth[k] + br * thd[k]
        end
        Fp[1] ~ kt * dl[1] + bt * dld[1]
        Fp[2] ~ kt * dl[2] + bt * dld[2]
        Fp[3] ~ tau
        # child.e = B^T [F; Fp]: (I - [g] + g g^T) F and R^T Fp
        gF ~ g[1] * F[1] + g[2] * F[2] + g[3] * F[3]
        child.e[1] ~ F[1] - (g[2] * F[3] - g[3] * F[2]) + g[1] * gF
        child.e[2] ~ F[2] - (g[3] * F[1] - g[1] * F[3]) + g[2] * gF
        child.e[3] ~ F[3] - (g[1] * F[2] - g[2] * F[1]) + g[3] * gF
        child.e[4] ~ R[1, 1] * Fp[1] + R[2, 1] * Fp[2] + R[3, 1] * Fp[3]
        child.e[5] ~ R[1, 2] * Fp[1] + R[2, 2] * Fp[2] + R[3, 2] * Fp[3]
        child.e[6] ~ R[1, 3] * Fp[1] + R[2, 3] * Fp[2] + R[3, 3] * Fp[3]
        # parent.e = -Ad(H)^-T child.e = -[R child.e_ang + p x Fp; Fp]
        parent.e[1] ~ -(R[1, 1] * child.e[1] + R[1, 2] * child.e[2] + R[1, 3] * child.e[3] +
                        (dl[2] * tau - q * Fp[2]))
        parent.e[2] ~ -(R[2, 1] * child.e[1] + R[2, 2] * child.e[2] + R[2, 3] * child.e[3] +
                        (q * Fp[1] - dl[1] * tau))
        parent.e[3] ~ -(R[3, 1] * child.e[1] + R[3, 2] * child.e[2] + R[3, 3] * child.e[3] +
                        (dl[1] * Fp[2] - dl[2] * Fp[1]))
        parent.e[4] ~ -Fp[1]
        parent.e[5] ~ -Fp[2]
        parent.e[6] ~ -Fp[3]
        drive.e ~ -tau
        drive.f ~ qdot
        qout ~ q
        qdout ~ qdot
        # pose = ((1, g), (dl_x, dl_y, q)): the chart H itself
        pose[1] ~ 1.0
        pose[2] ~ g[1]
        pose[3] ~ g[2]
        pose[4] ~ g[3]
        pose[5] ~ dl[1]
        pose[6] ~ dl[2]
        pose[7] ~ q
        dang[1] ~ dth[1]
        dang[2] ~ dth[2]
        dang[3] ~ dth[3]
        dlin[1] ~ dl[1]
        dlin[2] ~ dl[2]
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
