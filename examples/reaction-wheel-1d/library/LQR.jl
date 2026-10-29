@block LQR begin
    @parameters begin
        K_theta::Real = 0.0, [unit = "V/rad", description = "Gain on the body angle"]
        K_thetadot::Real = 0.0, [unit = "V*s/rad", description = "Gain on the body angular velocity"]
        K_wheel::Real = 0.0, [unit = "V*s/rad", description = "Gain on the wheel speed relative to the body"]
        u_max::Real = 12.0, [unit = "V", min = 0, description = "Voltage limit"]
    end
    @inputs begin
        theta::Real
        thetadot::Real
        w_rel::Real
    end
    @outputs u::Real = 0.0, [unit = "V"]
    # u = clamp(-K * [theta, thetadot, w_rel], -u_max, u_max): the parameters are the
    # entries of the discrete Riccati gain K, so design/design.py writes them verbatim.
    # The firmware samples at 2 ms and holds u until the next tick.
    @discrete Ts = 2e-3 begin
        u = clamp(
            -(K_theta * theta + K_thetadot * thetadot + K_wheel * w_rel),
            -u_max,
            u_max,
        )
    end
end
