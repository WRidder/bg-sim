@block LQR begin
    @parameters begin
        K_x::Real = -70.7107, [unit = "N/m", description = "Riccati gain on the cart position"]
        K_v::Real = -44.7664, [unit = "N*s/m", description = "Riccati gain on the cart speed"]
        K_theta::Real = -150.0957, [unit = "N", description = "Riccati gain on the pendulum angle"]
        K_omega::Real = -33.5132, [unit = "N*s", description = "Riccati gain on the pendulum rate"]
        u_max::Real = 20.0, [unit = "N", min = 0, description = "Force limit"]
    end
    @inputs begin
        x::Real
        v::Real
        theta::Real
        w::Real
        x_ref::Real
    end
    @outputs u::Real = 0.0, [unit = "N"]
    # u = clamp(-K * [x - x_ref, v, theta, w], -u_max, u_max); the parameters are the
    # entries of the Riccati gain vector K (they are all negative for this plant and sign
    # convention), so design/design.py writes them verbatim. The firmware samples at 1 ms.
    @discrete Ts = 1e-3 begin
        u = clamp(
            -(K_x * (x - x_ref) + K_v * v + K_theta * theta + K_omega * w),
            -u_max,
            u_max,
        )
    end
end
