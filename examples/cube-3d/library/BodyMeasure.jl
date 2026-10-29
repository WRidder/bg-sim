@block BodyMeasure begin
    # World-frame measurement of one rigid body (X-MB4): a sensor, not plant physics.
    #
    # Inputs are the body momentum `P = [J w; m v]` (body frame, the `RigidBody3D` output `P`)
    # and the composed world pose `g = (q_w, q_x, q_y, q_z, p)` of the body frame. Outputs:
    #
    #   H  = R P_ang + p x (R P_lin)          angular momentum about the world origin (the pivot)
    #   tg = p x (0, 0, -m g0)                gravity torque of this body about the world origin
    #   Ig = integral of tg dt                the gravity angular impulse (starts at 0; the z component is
    #                                         identically 0, a vertical force has no vertical torque)
    #
    # Summed over every body of the rig, `H_total(t) - Ig_total(t)` is the angular momentum
    # minus the gravity impulse, so it is constant exactly when d/dt H_total equals the
    # gravity torque about the pivot (the gravity-off model has `g0 = 0` and `tg = 0`).
    @inputs begin
        P::Vec{6}
        g::Vec{7}
    end
    @outputs begin
        H::Vec{3}
        tg::Vec{3}
        Ig::Vec{3}
    end
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @variables begin
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        vx::Real = 0.0, [description = "Linear momentum (world), x"]
        vy::Real = 0.0, [description = "Linear momentum (world), y"]
        vz::Real = 0.0, [description = "Linear momentum (world), z"]
        Ix::Real = 0.0, [state = :prefer, description = "Gravity impulse x"]
        Iy::Real = 0.0, [state = :prefer, description = "Gravity impulse y"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        vx ~ R[1, 1] * P[4] + R[1, 2] * P[5] + R[1, 3] * P[6]
        vy ~ R[2, 1] * P[4] + R[2, 2] * P[5] + R[2, 3] * P[6]
        vz ~ R[3, 1] * P[4] + R[3, 2] * P[5] + R[3, 3] * P[6]
        H[1] ~ R[1, 1] * P[1] + R[1, 2] * P[2] + R[1, 3] * P[3] + g[6] * vz - g[7] * vy
        H[2] ~ R[2, 1] * P[1] + R[2, 2] * P[2] + R[2, 3] * P[3] + g[7] * vx - g[5] * vz
        H[3] ~ R[3, 1] * P[1] + R[3, 2] * P[2] + R[3, 3] * P[3] + g[5] * vy - g[6] * vx
        tg[1] ~ -m * g0 * g[6]
        tg[2] ~ m * g0 * g[5]
        tg[3] ~ 0.0 * g[5]
        ddt(Ix) ~ tg[1]
        ddt(Iy) ~ tg[2]
        Ig[1] ~ Ix
        Ig[2] ~ Iy
        Ig[3] ~ 0.0 * g[5]
    end
end
