@block LsmController begin
    # Speed controller of the linear synchronous motor: thrust command from the speed profile.
    #   F_cmd = m*a_ref + k_aero*v_ref^2 + Kp*(e + x),  e = v_ref - v,  dx/dt = e/Ti
    # (feedforward of the acceleration and of the aerodynamic drag, PI on the speed error), limited to
    # +-F_max with the integrator held while the limit is active.
    @inputs begin
        v_ref::Real, [unit = "m/s", description = "Speed reference"]
        a_ref::Real, [unit = "m/s^2", description = "Acceleration of the reference"]
        v::Real, [unit = "m/s", description = "Measured speed"]
    end
    @outputs F_cmd::Real, [unit = "N", description = "Thrust command"]
    @parameters begin
        m::Real = 53000.0, [unit = "kg", min = 0, description = "Vehicle mass for the acceleration feedforward"]
        k_aero::Real = 2.5, [unit = "N*s^2/m^2", min = 0, description = "Drag coefficient 0.5*rho*Cd*A"]
        Kp::Real = 3.0e4, [unit = "N*s/m", min = 0, description = "Proportional gain"]
        Ti::Real = 4.0, [unit = "s", min = 1.0e-9, description = "Integral time"]
        F_max::Real = 1.5e5, [unit = "N", min = 0, description = "Thrust limit"]
    end
    @variables begin
        x::Real = 0.0, [unit = "m/s", state = :prefer, description = "Integral state"]
        F_u::Real = 0.0, [unit = "N", description = "Unlimited thrust command"]
    end
    @equations begin
        F_u ~ m * a_ref + k_aero * v_ref * v_ref + Kp * ((v_ref - v) + x)
        F_cmd ~ clamp(F_u, -F_max, F_max)
        ddt(x) ~ ifelse(abs(F_u) > F_max, 0.0, (v_ref - v) / Ti)
    end
end
