@block GyroSense begin
    # The Gyrover's states in the paper's coordinates (Tsai, Ferreira and Paredis, IROS 1999),
    # measured on the bond graph: the wheel's world pose `g` and body twist `V` (body z = axle,
    # body x = forward at the start), the axle joint (pendulum against wheel) and the tilt joint
    # (gimbal against pendulum, oriented so that its angle is the paper's theta2).
    #
    # With `a` the axle and `ex` the wheel's x axis in the world, the lean frame of the docs is
    #
    #     lean  = asin(a_z),               A_x = (a_y, -a_x, 0) / cos(lean)   (heading direction)
    #     B_z   = A_x x a                  (the wheel's "up" in its own plane)
    #     gamma = atan(-ex . B_z, ex . A_x)                                    (wheel angle)
    #     theta1 = gamma + q_axle          (the pendulum's pitch in the lean frame, wrapped)
    #
    # and the rates follow from the world angular velocity `w = R V[1:3]` of the wheel:
    # roll rate `w . A_x`, yaw rate in the wheel plane `w . B_z`, wheel rate `V[3]` (about the
    # axle) and heading rate `(w_z - V[3] a_z) / cos(lean)^2`, integrated into `heading`
    # (no wrap). Same outputs, names and signs as the reference block `GyroverRef`.
    # `spin_vis` is the flywheel angle slowed down `slow` times for the 3D view (the real
    # 250 rev/s would alias at any frame rate).
    @parameters begin
        R::Real = 0.197, [unit = "m", min = 0, description = "Wheel radius (for the speed)"]
        slow::Real = 200.0, [unit = "1", min = 1, description = "Slow-down of the displayed flywheel spin"]
    end
    @inputs begin
        g::Vec{7}
        V::Vec{6}
        qa::Real
        qda::Real
        qt::Real
        qdt::Real
        w3::Real
    end
    @variables begin
        psi::Real = 0.0, [unit = "rad", state = :prefer, description = "Heading (integrated)"]
        spin::Real = 0.0, [unit = "rad", state = :prefer, description = "Displayed flywheel angle"]
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
        Rm::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Wheel rotation"]
        w::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Wheel angular velocity in the world"]
        ch::Real = 1.0, [unit = "1", description = "cos(lean)"]
        Ax::Vec{3} = [1.0, 0.0, 0.0], [unit = "1", description = "Heading direction"]
        Bz::Vec{3} = [0.0, 0.0, 1.0], [unit = "1", description = "Wheel-plane up direction"]
        gam::Real = 0.0, [unit = "rad", description = "Wheel angle"]
    end
    @outputs begin
        lean::Real, [unit = "rad", description = "Lean from upright (paper theta0 - pi/2)"]
        heading::Real, [unit = "rad", description = "Heading psi"]
        th1::Real, [unit = "rad", description = "Pendulum angle (paper theta1)"]
        w1::Real, [unit = "rad/s", description = "Pendulum rate relative to the wheel (paper w1)"]
        wz::Real, [unit = "rad/s", description = "Wheel rate about the axle (paper omega0z)"]
        th2::Real, [unit = "rad", description = "Tilt angle (paper theta2)"]
        w2::Real, [unit = "rad/s", description = "Tilt rate (paper w2)"]
        wx::Real, [unit = "rad/s", description = "Roll rate (paper omega0x)"]
        wy::Real, [unit = "rad/s", description = "Yaw rate in the wheel plane (paper omega0y)"]
        yaw_rate::Real, [unit = "rad/s", description = "Heading rate"]
        v::Real, [unit = "m/s", description = "Forward speed R wz"]
        xc::Real, [unit = "m", description = "Wheel centre x"]
        yc::Real, [unit = "m", description = "Wheel centre y"]
        spin_vis::Real, [unit = "rad", description = "Flywheel angle for the 3D view, slowed down by `slow`"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        Rm[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        Rm[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        Rm[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        Rm[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        Rm[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        Rm[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        Rm[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        Rm[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        Rm[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        for i in 1:3
            w[i] ~ Rm[i, 1] * V[1] + Rm[i, 2] * V[2] + Rm[i, 3] * V[3]
        end
        ch ~ sqrt(Rm[1, 3] * Rm[1, 3] + Rm[2, 3] * Rm[2, 3])
        Ax[1] ~ Rm[2, 3] / ch
        Ax[2] ~ -Rm[1, 3] / ch
        Ax[3] ~ 0.0
        Bz[1] ~ Ax[2] * Rm[3, 3]
        Bz[2] ~ -Ax[1] * Rm[3, 3]
        Bz[3] ~ Ax[1] * Rm[2, 3] - Ax[2] * Rm[1, 3]
        gam ~ atan(-(Rm[1, 1] * Bz[1] + Rm[2, 1] * Bz[2] + Rm[3, 1] * Bz[3]), Rm[1, 1] * Ax[1] + Rm[2, 1] * Ax[2])
        lean ~ asin(Rm[3, 3])
        th1 ~ atan(sin(gam + qa), cos(gam + qa))
        w1 ~ qda
        wz ~ V[3]
        th2 ~ qt
        w2 ~ qdt
        wx ~ w[1] * Ax[1] + w[2] * Ax[2]
        wy ~ w[1] * Bz[1] + w[2] * Bz[2] + w[3] * Bz[3]
        yaw_rate ~ (w[3] - V[3] * Rm[3, 3]) / (ch * ch)
        ddt(psi) ~ yaw_rate
        heading ~ psi
        v ~ R * V[3]
        xc ~ g[5]
        yc ~ g[6]
        ddt(spin) ~ w3 / slow
        spin_vis ~ spin
    end
end
