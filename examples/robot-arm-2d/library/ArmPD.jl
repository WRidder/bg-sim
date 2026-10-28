@block ArmPD begin
    # 1 ms PD + gravity feedforward for the planar 2-link arm (X-MB2). The firmware
    # samples the two joint angles and rates and holds the torque until the next tick,
    # so the drive is a zero-order hold and no algebraic loop closes through the plant.
    #
    #   e_i  = ref_i - q_i
    #   G_1  = g0 (m1 lc1 cos q1 + m2 (L1 cos q1 + lc2 cos(q1 + q2)))
    #   G_2  = g0 m2 lc2 cos(q1 + q2)
    #   u_i  = clamp(Kp_i e_i - Kd_i qd_i + G_i, -u_i_max, u_i_max)
    #
    # The feedforward `G` is the gravity torque about each joint at the sampled
    # configuration, so a settled arm sits at the reference angle instead of at the
    # PD droop `G / Kp`; the clamp is a torque limit (a real actuator, and it keeps the
    # torque transient of the reference step finite). The derivative acts on the
    # measurement (`-Kd qd`), not on the error, so a reference step does not produce a
    # derivative kick. `clamp` inside `@discrete` is plain generated code, not a
    # symbolic `ifelse`, so it creates no event callback.
    @parameters begin
        Kp1::Real = 250.0, [unit = "N*m/rad", min = 0, description = "Joint 1 proportional gain"]
        Kd1::Real = 26.0, [unit = "N*m*s/rad", min = 0, description = "Joint 1 rate gain"]
        Kp2::Real = 30.0, [unit = "N*m/rad", min = 0, description = "Joint 2 proportional gain"]
        Kd2::Real = 3.0, [unit = "N*m*s/rad", min = 0, description = "Joint 2 rate gain"]
        m1::Real = 2.0, [unit = "kg", min = 0, description = "Link 1 mass"]
        m2::Real = 1.5, [unit = "kg", min = 0, description = "Link 2 mass including the payload"]
        L1::Real = 0.4, [unit = "m", min = 0, description = "Link 1 length (pivot to elbow)"]
        lc1::Real = 0.2, [unit = "m", min = 0, description = "Link 1 centre of mass from the shoulder"]
        lc2::Real = 0.2, [unit = "m", min = 0, description = "Link 2 centre of mass from the elbow"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        u1max::Real = 30.0, [unit = "N*m", min = 0, description = "Joint 1 torque limit"]
        u2max::Real = 10.0, [unit = "N*m", min = 0, description = "Joint 2 torque limit"]
    end
    @inputs begin
        q1::Real
        q2::Real
        qd1::Real
        qd2::Real
        ref1::Real
        ref2::Real
    end
    @outputs begin
        u1::Real = 0.0
        u2::Real = 0.0
        e1::Real = 0.0
        e2::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        e1 = ref1 - q1
        e2 = ref2 - q2
        G1 = g0 * (m1 * lc1 * cos(q1) + m2 * (L1 * cos(q1) + lc2 * cos(q1 + q2)))
        G2 = g0 * m2 * lc2 * cos(q1 + q2)
        u1 = clamp(Kp1 * e1 - Kd1 * qd1 + G1, -u1max, u1max)
        u2 = clamp(Kp2 * e2 - Kd2 * qd2 + G2, -u2max, u2max)
    end
end
