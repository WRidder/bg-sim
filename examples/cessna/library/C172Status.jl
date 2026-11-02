@block C172Status begin
    # What the cessna-sim host reads (signal only): the pose in the host's units and the
    # instrument values of the six-pack.
    #
    #   north_m, east_m, alt_m   world position (the world is x north, y west, z up)
    #   q_w .. q_z               attitude quaternion, body (x forward, y left, z up) to world
    #   phi_deg, theta_deg       bank and pitch; psi_deg the heading 0 .. 360
    #   kias, ktas               calibrated (the airspeed indicator: no position error) and true
    #                            airspeed in knots; vs_fpm the vertical speed in ft/min
    #   alt_ft                   altimeter (standard pressure: the ISA altitude), agl_ft above the
    #                            runway (the wheels: the CG height minus its static height)
    #   turn_dps                 the turn coordinator's rate of turn (heading rate, deg/s)
    #   slip                     the ball: the aerodynamic side force over the weight (positive:
    #                            ball right; the wheels' side force on the runway is left out)
    #   on_ground                1 while any wheel carries more than 10 N
    @inputs begin
        g::Vec{7}
        cas::Real, [unit = "m/s"]
        vt::Real, [unit = "m/s"]
        hdot::Real, [unit = "m/s"]
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        fy::Real, [unit = "N", description = "Aerodynamic side force (body y, left)"]
        fn_nose::Real, [unit = "N"]
        fn_left::Real, [unit = "N"]
        fn_right::Real, [unit = "N"]
    end
    @outputs begin
        north_m::Real, [unit = "m"]
        east_m::Real, [unit = "m"]
        alt_m::Real, [unit = "m"]
        q_w::Real
        q_x::Real
        q_y::Real
        q_z::Real
        phi_deg::Real
        theta_deg::Real
        psi_deg::Real
        kias::Real
        ktas::Real
        vs_fpm::Real
        alt_ft::Real
        agl_ft::Real
        turn_dps::Real
        slip::Real
        on_ground::Real
    end
    @parameters begin
        ground_z::Real = 0.0, [unit = "m"]
        h_cg0::Real = 1.2546, [unit = "m", description = "Static CG height above the runway"]
        mass::Real = 1088.62, [unit = "kg"]
        g0::Real = 9.80665, [unit = "m/s^2"]
        f_ground::Real = 10.0, [unit = "N"]
        one_ms::Real = 1.0, [unit = "m/s"]
        one_m::Real = 1.0, [unit = "m"]
        one_rads::Real = 1.0, [unit = "rad/s"]
    end
    @equations begin
        north_m ~ g[5]
        east_m ~ -g[6]
        alt_m ~ g[7]
        q_w ~ g[1]
        q_x ~ g[2]
        q_y ~ g[3]
        q_z ~ g[4]
        phi_deg ~ phi * 57.29577951308232
        theta_deg ~ theta * 57.29577951308232
        psi_deg ~ psi * 57.29577951308232 + 360.0 - 360.0 * floor((psi * 57.29577951308232 + 360.0) / 360.0)
        kias ~ cas / one_ms / 0.514444444
        ktas ~ vt / one_ms / 0.514444444
        vs_fpm ~ hdot / one_ms / 0.3048 * 60.0
        alt_ft ~ g[7] / one_m / 0.3048
        agl_ft ~ (g[7] - ground_z - h_cg0) / one_m / 0.3048
        turn_dps ~ (q * sin(phi) + r * cos(phi)) / cos(theta) / one_rads * 57.29577951308232
        slip ~ fy / (mass * g0)
        on_ground ~ ifelse(fn_nose + fn_left + fn_right > f_ground, 1.0, 0.0)
    end
end
