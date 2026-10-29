@block Free3D begin
    # Free (6-DOF) spatial joint, **fixed structure** (J-MB9 correction, n = 6, no complement):
    # `S = I6`. The six ports use the **relative body-frame twist components as quasi-velocities**:
    # three **Rotation** ports (`drive1..3`, `drive_k.f = V_rel[k]`, the relative angular velocity)
    # and three **Translation** ports (`drive4..6`, `drive_k.f = V_rel[k]`, the relative linear
    # velocity in the child frame).
    #
    # The relative pose is **stored as an integrated quaternion plus the child origin in the
    # parent frame** (D-MB6, no Euler angles, no gimbal lock), with the tangent-space RHS of
    # `PoseIntegrator3D`:
    #
    #     V_rel = child.f - Ad(g)^-1 parent.f,     g = (R(Q), p)
    #     ddt(Q) = 0.5 Q (x) [0, V_rel[1:3]],      ddt(p) = R(Q) V_rel[4:6]
    #
    # (`R V_rel[4:6]` is the child-origin velocity relative to the parent frame, so `q.qdot = 0`
    # identically). There is nothing to constrain: `child.e = -drive.e` componentwise,
    # `parent.e = -Ad(g)^-T child.e`, and the port power
    # `parent.e.parent.f + child.e.child.f + sum drive_k.e*drive_k.f` is identically zero.
    # `GroundSpatial -> Free3D -> RigidBody3D` is a floating body whose pose is `pose`.
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive1::Power{Rotation}
        drive2::Power{Rotation}
        drive3::Power{Rotation}
        drive4::Power{Translation}
        drive5::Power{Translation}
        drive6::Power{Translation}
    end
    @variables begin
qw::Real = 1.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion scalar part (child in parent)"]
qx::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion x"]
qy::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion y"]
qz::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion z"]
s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the relative orientation (child to parent)"]
        px::Real = 0.0, [unit = "m", state = :prefer, description = "Child origin x in the parent frame"]
        py::Real = 0.0, [unit = "m", state = :prefer, description = "Child origin y in the parent frame"]
        pz::Real = 0.0, [unit = "m", state = :prefer, description = "Child origin z in the parent frame"]
        u::Vec{3} = [0.0, 0.0, 0.0], [description = "parent.f[4:6] - p x parent.f[1:3]"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        Wl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Linear wrench rotated into the parent frame"]
        Wa::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Angular wrench rotated into the parent frame"]
    end
    @outputs begin
        qrel::Vec{4}
        pose::Vec{7}
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
        u[1] ~ parent.f[4] - (py * parent.f[3] - pz * parent.f[2])
        u[2] ~ parent.f[5] - (pz * parent.f[1] - px * parent.f[3])
        u[3] ~ parent.f[6] - (px * parent.f[2] - py * parent.f[1])
        Vrel[1] ~ child.f[1] - (R[1, 1] * parent.f[1] + R[2, 1] * parent.f[2] + R[3, 1] * parent.f[3])
        Vrel[4] ~ child.f[4] - (R[1, 1] * u[1] + R[2, 1] * u[2] + R[3, 1] * u[3])
        Vrel[2] ~ child.f[2] - (R[1, 2] * parent.f[1] + R[2, 2] * parent.f[2] + R[3, 2] * parent.f[3])
        Vrel[5] ~ child.f[5] - (R[1, 2] * u[1] + R[2, 2] * u[2] + R[3, 2] * u[3])
        Vrel[3] ~ child.f[3] - (R[1, 3] * parent.f[1] + R[2, 3] * parent.f[2] + R[3, 3] * parent.f[3])
        Vrel[6] ~ child.f[6] - (R[1, 3] * u[1] + R[2, 3] * u[2] + R[3, 3] * u[3])
ddt(qw) ~ -0.5 * (Vrel[1] * qx + Vrel[2] * qy + Vrel[3] * qz)
ddt(qx) ~ 0.5 * (Vrel[1] * qw + Vrel[3] * qy - Vrel[2] * qz)
ddt(qy) ~ 0.5 * (Vrel[2] * qw + Vrel[1] * qz - Vrel[3] * qx)
ddt(qz) ~ 0.5 * (Vrel[3] * qw + Vrel[2] * qx - Vrel[1] * qy)
        ddt(px) ~ R[1, 1] * Vrel[4] + R[1, 2] * Vrel[5] + R[1, 3] * Vrel[6]
        ddt(py) ~ R[2, 1] * Vrel[4] + R[2, 2] * Vrel[5] + R[2, 3] * Vrel[6]
        ddt(pz) ~ R[3, 1] * Vrel[4] + R[3, 2] * Vrel[5] + R[3, 3] * Vrel[6]
        child.e[1] ~ -drive1.e
        child.e[2] ~ -drive2.e
        child.e[3] ~ -drive3.e
        child.e[4] ~ -drive4.e
        child.e[5] ~ -drive5.e
        child.e[6] ~ -drive6.e
        for k in 1:3
            Wa[k] ~ R[k, 1] * child.e[1] + R[k, 2] * child.e[2] + R[k, 3] * child.e[3]
            Wl[k] ~ R[k, 1] * child.e[4] + R[k, 2] * child.e[5] + R[k, 3] * child.e[6]
        end
        # parent.e = -[R W_ang + p x (R W_lin); R W_lin]
        parent.e[1] ~ -(Wa[1] + (py * Wl[3] - pz * Wl[2]))
        parent.e[2] ~ -(Wa[2] + (pz * Wl[1] - px * Wl[3]))
        parent.e[3] ~ -(Wa[3] + (px * Wl[2] - py * Wl[1]))
        parent.e[4] ~ -Wl[1]
        parent.e[5] ~ -Wl[2]
        parent.e[6] ~ -Wl[3]
        drive1.f ~ Vrel[1]
        drive2.f ~ Vrel[2]
        drive3.f ~ Vrel[3]
        drive4.f ~ Vrel[4]
        drive5.f ~ Vrel[5]
        drive6.f ~ Vrel[6]
        qrel[1] ~ qw
        qrel[2] ~ qx
        qrel[3] ~ qy
        qrel[4] ~ qz
        pose[1] ~ qw
        pose[2] ~ qx
        pose[3] ~ qy
        pose[4] ~ qz
        pose[5] ~ px
        pose[6] ~ py
        pose[7] ~ pz
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
        drive4 => :flow_out
        drive5 => :flow_out
        drive6 => :flow_out
    end
end
