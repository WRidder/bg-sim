@block GCommand begin
    # Pilot stick to pitch-rate command, with the envelope protection (a min-select limiter).
    #
    # g-command (rate_mode = 0): the stick asks for a load factor nz_stick = 1 + nz_per_stick*stick
    # and the pitch rate that holds it in a steady pull-up,
    #     q_stick = g0/vt * (nz_stick - cos(gamma) cos(phi))            (rad/s, output in deg/s)
    # Pitch-rate command (rate_mode = 1): q_stick = q_per_stick * stick (deg/s).
    #
    # The limiter (limiter = 1) takes the smallest of three pitch-rate demands:
    #     q_alpha = k_alim * (alpha_max - alpha)                    (alpha limiter, deg/s)
    #     q_g     = g0/vt * (nz_max - cos(gamma) cos(phi)) + k_glim * (nz_max - nz)   (g limiter)
    #     q_cmd   = min(q_stick, q_alpha, q_g)
    # so the pitch rate fades out as alpha or nz approaches its limit, whatever the stick says.
    # With limiter = 0 the stick goes straight through. Pushing (negative q demands) is not
    # limited.
    @inputs begin
        stick::Real, [description = "Pitch stick, -1 (full forward) .. +1 (full aft)"]
        vt::Real, [unit = "m/s", description = "True airspeed"]
        alpha::Real, [description = "Angle of attack (deg)"]
        nz::Real, [description = "Load factor (g)"]
        gamma::Real, [unit = "rad", description = "Flight-path angle"]
        phi::Real, [unit = "rad", description = "Roll angle"]
    end
    @outputs begin
        q_cmd::Real, [description = "Pitch-rate command to the control law (deg/s)"]
        q_stick::Real, [description = "Pitch rate the stick asks for (deg/s)"]
        q_alpha::Real, [description = "Alpha-limiter pitch-rate ceiling (deg/s)"]
        q_g::Real, [description = "g-limiter pitch-rate ceiling (deg/s)"]
    end
    @parameters begin
        g0::Real = 9.80665, [unit = "m/s^2", description = "Gravity"]
        nz_per_stick::Real = 10.0, [description = "Load factor per unit stick (g), g-command"]
        q_per_stick::Real = 40.0, [description = "Pitch rate per unit stick (deg/s), rate command"]
        rate_mode::Real = 0.0, [tunable = true, description = "0: g-command, 1: pitch-rate command"]
        limiter::Real = 1.0, [tunable = true, description = "1: limiter on, 0: off"]
        alpha_max::Real = 25.0, [description = "Alpha limit (deg)"]
        nz_max::Real = 9.0, [description = "Load-factor limit (g)"]
        k_alim::Real = 3.0, [description = "Alpha-limiter gain ((deg/s)/deg)"]
        k_glim::Real = 4.0, [description = "g-limiter gain ((deg/s)/g)"]
    end
    @variables begin
        cg::Real = 1.0, [description = "cos(gamma) cos(phi): the 1 g of a level pull-up"]
        q_lim::Real = 0.0, [description = "The smaller limiter ceiling (deg/s)"]
    end
    @equations begin
        cg ~ cos(gamma) * cos(phi)
        q_stick ~ ifelse(rate_mode > 0.5, q_per_stick * stick,
            g0 / vt * (1.0 + nz_per_stick * stick - cg) * 57.29577951308232)
        q_alpha ~ k_alim * (alpha_max - alpha)
        q_g ~ g0 / vt * (nz_max - cg) * 57.29577951308232 + k_glim * (nz_max - nz)
        q_lim ~ min(q_alpha, q_g)
        q_cmd ~ ifelse(limiter > 0.5, min(q_stick, q_lim), q_stick)
    end
end
