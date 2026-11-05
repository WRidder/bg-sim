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
    #                departure from controlled flight; the host latches it), else 0. Never on
    #                the ground, where alpha and beta of a slow aircraft mean nothing.
    #   ground       1 when the airframe itself meets the ground: the altitude is below h_ground
    #                (flat ground), or a leg is compressed past `stroke` (the gear has bottomed)
    #   on_ground    1 while the wheels carry more than f_ground
    #   nz_total     load factor with the wheels' normal force: 1 g when parked, nz in the air
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
        nz::Real, [description = "Load factor of the aerodynamic force (g)"]
        fn_nose::Real, [unit = "N"]
        fn_left::Real, [unit = "N"]
        fn_right::Real, [unit = "N"]
        q_nose::Real, [unit = "m", description = "Strut compression"]
        q_left::Real, [unit = "m"]
        q_right::Real, [unit = "m"]
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
        on_ground::Real
        nz_total::Real
    end
    @parameters begin
        a0::Real = 340.4, [unit = "m/s", description = "Sea-level speed of sound of the book's atmosphere"]
        p0::Real = 101375.0, [unit = "Pa", description = "Sea-level pressure of the book's atmosphere"]
        alpha_hi::Real = 35.0, [description = "Departure: alpha above this (deg)"]
        alpha_lo::Real = -15.0, [description = "Departure: alpha below this (deg)"]
        beta_max::Real = 15.0, [description = "Departure: |beta| above this (deg)"]
        h_ground::Real = 0.0, [unit = "m", description = "Ground altitude"]
        mass::Real = 9295.44, [unit = "kg"]
        g0::Real = 9.805416, [unit = "m/s^2"]
        f_ground::Real = 100.0, [unit = "N", description = "Wheel load above which the aircraft is on the ground"]
        stroke::Real = 0.4, [unit = "m", description = "Compression at which a leg bottoms"]
    end
    @variables begin
        m2::Real = 0.0
        qc::Real = 0.0, [unit = "Pa", description = "Impact pressure"]
        fn::Real = 0.0, [unit = "N", description = "Total wheel load"]
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
        fn ~ fn_nose + fn_left + fn_right
        on_ground ~ ifelse(fn > f_ground, 1.0, 0.0)
        nz_total ~ nz + fn / (mass * g0)
        departed ~ ifelse(fn > f_ground, 0.0, ifelse(alpha > alpha_hi, 1.0, ifelse(alpha < alpha_lo, 1.0, ifelse(abs(beta) > beta_max, 1.0, 0.0))))
        ground ~ ifelse(h < h_ground, 1.0, ifelse(q_nose > stroke, 1.0, ifelse(q_left > stroke, 1.0, ifelse(q_right > stroke, 1.0, 0.0))))
    end
end
