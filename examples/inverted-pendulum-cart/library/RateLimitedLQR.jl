@block RateLimitedLQR begin
    # The LQR balance law with the actuator's slew limit in the 1 ms firmware:
    #   u_cmd = clamp(-K [x - x_ref, v, theta, w], -u_max, u_max)
    #   u     = clamp(u_prev + clamp(u_cmd - u_prev, -du_max, du_max), -u_max, u_max)
    # This is the fair comparison for the MPC: the same state feedback, but the force
    # can only change by du_max per sample and the future is not planned.
    @parameters begin
        K_x::Real = -89.442719, [unit = "N/m", description = "Riccati gain on the cart position"]
        K_v::Real = -54.686555, [unit = "N*s/m", description = "Riccati gain on the cart speed"]
        K_theta::Real = -175.121631, [unit = "N", description = "Riccati gain on the pendulum angle"]
        K_omega::Real = -39.152990, [unit = "N*s", description = "Riccati gain on the pendulum rate"]
        u_max::Real = 20.0, [unit = "N", min = 0, description = "Force limit"]
        du_max::Real = 0.2, [unit = "N", min = 0, description = "Force increment per 1 ms sample"]
    end
    @inputs begin
        x::Real, [unit = "m"]
        v::Real, [unit = "m/s"]
        theta::Real, [unit = "rad"]
        w::Real, [unit = "rad/s"]
        x_ref::Real, [unit = "m"]
    end
    @outputs u::Real = 0.0, [unit = "N"]
    @variables u_prev::Real = 0.0, [unit = "N", description = "Force applied on the previous tick"]
    @discrete Ts = 1e-3 begin
        u_cmd = clamp(
            -(K_x * (x - x_ref) + K_v * v + K_theta * theta + K_omega * w),
            -u_max,
            u_max,
        )
        u = clamp(u_prev + clamp(u_cmd - u_prev, -du_max, du_max), -u_max, u_max)
        u_prev = u
    end
end
