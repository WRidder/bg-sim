@block PitchPI begin
    # The gain-scheduled collective-pitch PI of the NREL 5 MW baseline controller (report section
    # 7.3 and the DISCON source of Appendix C, signal only), on the filtered generator speed w:
    #
    #   e = w - w_ref
    #   GK = 1 / (1 + beta / beta_k)             gain correction: the pitch sensitivity dP/dbeta
    #                                            grows about linearly with the pitch (Table 7-1)
    #   beta_cmd = clamp(GK (kp e + ki xi), beta_min, beta_max),   d(xi)/dt = e
    #
    # The integrator is held inside [beta_min, beta_max] / (GK ki), as DISCON clamps it, so it does
    # not wind up below rated (e < 0, beta_cmd = beta_min) or at the top stop. DISCON schedules on
    # its last pitch command; here GK reads the measured pitch beta (the actuator output), which
    # avoids an algebraic loop and differs from the command only by the actuator lag.
    @inputs begin
        w::Real, [unit = "rad/s", description = "Filtered generator speed"]
        beta::Real, [unit = "rad", description = "Measured blade pitch (gain scheduling)"]
    end
    @outputs begin
        beta_cmd::Real, [unit = "rad", description = "Pitch command"]
        gk::Real, [description = "Gain-correction factor"]
    end
    @parameters begin
        w_ref::Real = 122.9096, [unit = "rad/s", description = "Rated generator speed (1173.7 rpm)"]
        kp::Real = 0.01882681, [unit = "s", min = 0, tunable = true, description = "Proportional gain at zero pitch"]
        ki::Real = 0.008068634, [min = 1.0e-9, tunable = true, description = "Integral gain at zero pitch"]
        beta_k::Real = 0.1099965, [unit = "rad", min = 1.0e-6, description = "Pitch at which the sensitivity has doubled (6.3 deg)"]
        beta_min::Real = 0.0, [unit = "rad", description = "Fine pitch"]
        beta_max::Real = 1.570796, [unit = "rad", description = "Feathered pitch"]
    end
    @variables begin
        xi::Real = 0.0, [unit = "rad", state = :prefer, description = "Integrated speed error (rad/s * s)"]
        e::Real = 0.0, [unit = "rad/s"]
        lo::Real = 0.0, [unit = "rad"]
        hi::Real = 0.0, [unit = "rad"]
    end
    @equations begin
        e ~ w - w_ref
        gk ~ 1.0 / (1.0 + max(beta, 0.0) / beta_k)
        lo ~ beta_min / (gk * ki)
        hi ~ beta_max / (gk * ki)
        ddt(xi) ~ ifelse(xi <= lo, max(e, 0.0), ifelse(xi >= hi, min(e, 0.0), e))
        beta_cmd ~ clamp(gk * (kp * e + ki * xi), beta_min, beta_max)
    end
end
