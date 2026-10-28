@block Balancer begin
    # 1 ms PD + gravity feedforward for the planar reaction-wheel balancer (X-MB2).
    #
    #   tau = clamp(G sin(theta) + Kp (theta - ref) + Kd theta_dot, -tau_max, tau_max)
    #   G   = g0 (m_b lc_b + m_w L_w)      (the gravity torque about the pivot)
    #
    # The motor torque acts on the wheel; the reaction `-tau` acts on the body, so the
    # body balance is `J_A theta_dd = -tau + G sin(theta)`. With the feedforward the
    # settled angle is the reference angle. At t = 0 nothing moves (theta = ref = 0) and
    # the wheel exchange starts when the reference pulse tilts the body.
    @parameters begin
        Kp::Real = 16.0, [unit = "N*m/rad", min = 0, description = "Angle gain"]
        Kd::Real = 4.0, [unit = "N*m*s/rad", min = 0, description = "Rate gain"]
        m_b::Real = 1.5, [unit = "kg", min = 0, description = "Body mass"]
        lc_b::Real = 0.3, [unit = "m", min = 0, description = "Body centre of mass above the pivot"]
        m_w::Real = 0.4, [unit = "kg", min = 0, description = "Wheel mass"]
        L_w::Real = 0.5, [unit = "m", min = 0, description = "Wheel axis above the pivot"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        tau_max::Real = 1.5, [unit = "N*m", min = 0, description = "Motor torque limit"]
    end
    @inputs begin
        theta::Real
        thetadot::Real
        ref::Real
    end
    @outputs begin
        tau::Real = 0.0
        e::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        e = theta - ref
        G = g0 * (m_b * lc_b + m_w * L_w) * sin(theta)
        tau = clamp(G + Kp * e + Kd * thetadot, -tau_max, tau_max)
    end
end
