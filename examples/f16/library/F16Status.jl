@block F16Status begin
    # What a flight-simulator host needs from the f16-sim FMU that the airframe does not output
    # directly (no physics):
    #
    #   q_w..q_z     attitude quaternion of the body (forward-right-down) in north-east-down axes,
    #                from the geometric body pose gB of the model's world (x north, y west, z up;
    #                body x forward, y left, z up): (qw, qx, -qy, -qz)
    #   north, east  position (m); the model's world y points west
    #   phi_deg..    Euler angles (deg), gamma (deg)
    #   cas          calibrated airspeed (m/s) from the impact pressure of the book's atmosphere:
    #                qc = pa ((1 + 0.2 M^2)^3.5 - 1) below Mach 1, the Rayleigh pitot formula above;
    #                cas = a0 sqrt(5 ((qc/p0 + 1)^(2/7) - 1))
    #   departed     1 when alpha leaves [alpha_lo, alpha_hi] or |beta| exceeds beta_max (a
    #                departure from controlled flight; the host latches it), else 0
    #   ground       1 when the altitude is below h_ground (contact with a flat ground), else 0
    @inputs begin
        gB::Vec{7}, [description = "Pose of the geometric body frame (qw, qx, qy, qz, x, y, z)"]
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        gamma::Real, [unit = "rad"]
        mach::Real
        pa::Real, [unit = "Pa", description = "Static pressure"]
        alpha::Real, [description = "Angle of attack (deg)"]
        beta::Real, [description = "Sideslip (deg)"]
        h::Real, [unit = "m", description = "Altitude"]
    end
    @outputs begin
        q_w::Real
        q_x::Real
        q_y::Real
        q_z::Real
        north::Real, [unit = "m"]
        east::Real, [unit = "m"]
        phi_deg::Real
        theta_deg::Real
        psi_deg::Real
        gamma_deg::Real
        cas::Real, [unit = "m/s"]
        departed::Real
        ground::Real
    end
    @parameters begin
        a0::Real = 340.4, [unit = "m/s", description = "Sea-level speed of sound of the book's atmosphere"]
        p0::Real = 101375.0, [unit = "Pa", description = "Sea-level pressure of the book's atmosphere"]
        alpha_hi::Real = 35.0, [description = "Departure: alpha above this (deg)"]
        alpha_lo::Real = -15.0, [description = "Departure: alpha below this (deg)"]
        beta_max::Real = 15.0, [description = "Departure: |beta| above this (deg)"]
        h_ground::Real = 0.0, [unit = "m", description = "Ground altitude"]
    end
    @variables begin
        m2::Real = 0.0
        qc::Real = 0.0, [unit = "Pa", description = "Impact pressure"]
    end
    @equations begin
        q_w ~ gB[1]
        q_x ~ gB[2]
        q_y ~ -gB[3]
        q_z ~ -gB[4]
        north ~ gB[5]
        east ~ -gB[6]
        phi_deg ~ phi * 57.29577951308232
        theta_deg ~ theta * 57.29577951308232
        psi_deg ~ psi * 57.29577951308232
        gamma_deg ~ gamma * 57.29577951308232
        m2 ~ mach * mach
        qc ~ pa * ifelse(mach <= 1.0, (1.0 + 0.2 * m2)^3.5 - 1.0,
            166.92158 * m2^3.5 / max(7.0 * m2 - 1.0, 1.0)^2.5 - 1.0)
        cas ~ a0 * sqrt(5.0 * ((qc / p0 + 1.0)^0.2857142857142857 - 1.0))
        departed ~ ifelse(alpha > alpha_hi, 1.0, ifelse(alpha < alpha_lo, 1.0, ifelse(abs(beta) > beta_max, 1.0, 0.0)))
        ground ~ ifelse(h < h_ground, 1.0, 0.0)
    end
end
