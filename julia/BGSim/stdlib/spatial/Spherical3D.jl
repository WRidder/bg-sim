@block Spherical3D begin
    # Spatial spherical (ball) joint, **fixed structure** (J-MB9 correction, n = 3): three
    # rotational freedoms with `S = [I3 | 0]` (identity columns). The three ports are
    # **Rotation** ports whose flows are the **relative body-frame angular velocity components**
    # (quasi-velocities, `drive_k.f = V_rel[k]`); they are not Euler-angle rates.
    #
    # The relative orientation is **stored as an integrated unit quaternion** `(qw, qx, qy, qz)`
    # (child in parent, start values `1, 0, 0, 0`) with the tangent-space right-hand side of
    # `PoseIntegrator3D`, `ddt(Q) = 0.5 Q (x) [0, V_rel[1:3]]`, so `Q . Qdot = 0` identically and
    # the norm drifts only by the solver's accumulation; there is no gimbal lock. No
    # `ManifoldProjection` is attached (same recorded deviation as `PoseIntegrator3D`).
    #
    #     V_rel = child.f - Ad(g)^-1 parent.f,  g = (R(Q), 0),  Ad^-1 = diag(R^T, R^T).
    #
    # The three translations are the hard directions: compliant `dl` (child frame), integral,
    # no W201, with the FIX-MB-5 transport by the absolute child rate:
    # `ddt(dl) = V_rel[4:6] - w_c x dl`. Wrench: `child.e = [tau | kt dl + bt V_rel[4:6]]`,
    # `parent.e = -diag(R, R) child.e`; the port power is exactly
    # `sum drive_k.e*drive_k.f + d/dt(1/2 kt|dl|^2) + bt|V_rel[4:6]|^2`.
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive1::Power{Rotation}
        drive2::Power{Rotation}
        drive3::Power{Rotation}
    end
    @parameters begin
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Pivot translational stiffness"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Pivot translational damping"]
    end
    @variables begin
qw::Real = 1.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion scalar part (child in parent)"]
qx::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion x"]
qy::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion y"]
qz::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion z"]
s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the relative orientation (child to parent)"]
        dl::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Translational deflection (child frame)"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        Wl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Linear wrench rotated into the parent frame"]
        Wa::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Angular wrench rotated into the parent frame"]
    end
    @outputs begin
        qrel::Vec{4}
        omega::Vec{3}
        pose::Vec{7}
        dlin::Vec{3}, [unit = "m"]
        Vrelout::Vec{6}
    end
    @equations begin
s ~ qw * qw + qx * qx + qy * qy + qz * qz
R[1, 1] ~ (qw * qw + qx * qx - qy * qy - qz * qz) / s
R[1, 2] ~ 2 * (qx * qy - qw * qz) / s
R[1, 3] ~ 2 * (qx * qz + qw * qy) / s
R[2, 1] ~ 2 * (qx * qy + qw * qz) / s
R[2, 2] ~ (qw * qw - qx * qx + qy * qy - qz * qz) / s
R[2, 3] ~ 2 * (qy * qz - qw * qx) / s
R[3, 1] ~ 2 * (qx * qz - qw * qy) / s
R[3, 2] ~ 2 * (qy * qz + qw * qx) / s
R[3, 3] ~ (qw * qw - qx * qx - qy * qy + qz * qz) / s
        Vrel[1] ~ child.f[1] - (R[1, 1] * parent.f[1] + R[2, 1] * parent.f[2] + R[3, 1] * parent.f[3])
        Vrel[4] ~ child.f[4] - (R[1, 1] * parent.f[4] + R[2, 1] * parent.f[5] + R[3, 1] * parent.f[6])
        Vrel[2] ~ child.f[2] - (R[1, 2] * parent.f[1] + R[2, 2] * parent.f[2] + R[3, 2] * parent.f[3])
        Vrel[5] ~ child.f[5] - (R[1, 2] * parent.f[4] + R[2, 2] * parent.f[5] + R[3, 2] * parent.f[6])
        Vrel[3] ~ child.f[3] - (R[1, 3] * parent.f[1] + R[2, 3] * parent.f[2] + R[3, 3] * parent.f[3])
        Vrel[6] ~ child.f[6] - (R[1, 3] * parent.f[4] + R[2, 3] * parent.f[5] + R[3, 3] * parent.f[6])
ddt(qw) ~ -0.5 * (Vrel[1] * qx + Vrel[2] * qy + Vrel[3] * qz)
ddt(qx) ~ 0.5 * (Vrel[1] * qw + Vrel[3] * qy - Vrel[2] * qz)
ddt(qy) ~ 0.5 * (Vrel[2] * qw + Vrel[1] * qz - Vrel[3] * qx)
ddt(qz) ~ 0.5 * (Vrel[3] * qw + Vrel[2] * qx - Vrel[1] * qy)
        ddt(dl[1]) ~ Vrel[4] - (child.f[2] * dl[3] - child.f[3] * dl[2])
        ddt(dl[2]) ~ Vrel[5] - (child.f[3] * dl[1] - child.f[1] * dl[3])
        ddt(dl[3]) ~ Vrel[6] - (child.f[1] * dl[2] - child.f[2] * dl[1])
        child.e[1] ~ -drive1.e
        child.e[2] ~ -drive2.e
        child.e[3] ~ -drive3.e
        child.e[4] ~ kt * dl[1] + bt * Vrel[4]
        child.e[5] ~ kt * dl[2] + bt * Vrel[5]
        child.e[6] ~ kt * dl[3] + bt * Vrel[6]
        Wa[1] ~ R[1, 1] * child.e[1] + R[1, 2] * child.e[2] + R[1, 3] * child.e[3]
        Wl[1] ~ R[1, 1] * child.e[4] + R[1, 2] * child.e[5] + R[1, 3] * child.e[6]
        parent.e[1] ~ -Wa[1]
        parent.e[4] ~ -Wl[1]
        Wa[2] ~ R[2, 1] * child.e[1] + R[2, 2] * child.e[2] + R[2, 3] * child.e[3]
        Wl[2] ~ R[2, 1] * child.e[4] + R[2, 2] * child.e[5] + R[2, 3] * child.e[6]
        parent.e[2] ~ -Wa[2]
        parent.e[5] ~ -Wl[2]
        Wa[3] ~ R[3, 1] * child.e[1] + R[3, 2] * child.e[2] + R[3, 3] * child.e[3]
        Wl[3] ~ R[3, 1] * child.e[4] + R[3, 2] * child.e[5] + R[3, 3] * child.e[6]
        parent.e[3] ~ -Wa[3]
        parent.e[6] ~ -Wl[3]
        drive1.f ~ Vrel[1]
        drive2.f ~ Vrel[2]
        drive3.f ~ Vrel[3]
        qrel[1] ~ qw
        qrel[2] ~ qx
        qrel[3] ~ qy
        qrel[4] ~ qz
        omega[1] ~ Vrel[1]
        omega[2] ~ Vrel[2]
        omega[3] ~ Vrel[3]
        # pose = (Q, R dl): the deflected origin
        pose[1] ~ qw
        pose[2] ~ qx
        pose[3] ~ qy
        pose[4] ~ qz
        pose[5] ~ R[1, 1] * dl[1] + R[1, 2] * dl[2] + R[1, 3] * dl[3]
        pose[6] ~ R[2, 1] * dl[1] + R[2, 2] * dl[2] + R[2, 3] * dl[3]
        pose[7] ~ R[3, 1] * dl[1] + R[3, 2] * dl[2] + R[3, 3] * dl[3]
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
        drive3 => :flow_out
    end
end
