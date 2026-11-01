@block PitchCommand begin
    # Pilot stick to pitch-rate command for the three-axis f16-sim law: the g-command of
    # `GCommand` with turn compensation, an asymmetric stick and a negative-g limit.
    #
    # The stick asks for a load factor (pull: nz_pull g per unit, push: nz_push g per unit), and
    # the turn compensation adds what a level turn at the present bank needs, so a neutral stick
    # holds the altitude in a turn:
    #     tc     = turn_comp * (1/cos(phi) - 1)          for cos(phi) >= 0.5 (bank up to 60 deg)
    #            = turn_comp * max(2 cos(phi), 0)        beyond: fades out to zero at 90 deg bank
    #     nz_cmd = 1 + nz_pull*stick (stick > 0) or 1 + nz_push*stick (stick < 0), + tc
    #     dn_cmd = nz_cmd - cos(gamma) cos(phi)     the load factor asked for above the path's 1 g
    #     dn     = nz - cos(theta) cos(phi)         the same, measured (zero in steady straight flight
    #                                               and in a steady level turn)
    #     q_stick = g0/vt * (dn_cmd + k_nzc clamp(dn_cmd - dn, -nzc_lim, nzc_lim))   (deg/s)
    # The first term is the pitch rate of the steady manoeuvre (GCommand's command); the g-error
    # term builds the load factor in about half a second instead of the airframe's path time
    # constant, so the altitude barely moves when the turn compensation comes in. The clamp keeps
    # the extra rate of a full-stick pull small, so it does not overdrive the alpha limiter.
    # The limiter (limiter = 1) is GCommand's min-select of the alpha and g ceilings, plus a floor
    # for pushing:
    #     q_cmd = max(min(q_stick, q_alpha, q_g), q_neg),
    #     q_neg = g0/vt * (nz_min - cos(gamma) cos(phi)) + k_glim * (nz_min - nz)
    # `lim_active` is 1 while the limiter holds the command below what the stick asks for (the
    # HUD's limit warning).
    @inputs begin
        stick::Real, [description = "Pitch stick, -1 (full forward) .. +1 (full aft)"]
        vt::Real, [unit = "m/s", description = "True airspeed"]
        alpha::Real, [description = "Angle of attack (deg)"]
        nz::Real, [description = "Load factor (g)"]
        gamma::Real, [unit = "rad", description = "Flight-path angle"]
        phi::Real, [unit = "rad", description = "Roll angle"]
        theta::Real, [unit = "rad", description = "Pitch angle"]
    end
    @outputs begin
        q_cmd::Real, [description = "Pitch-rate command to the control law (deg/s)"]
        q_stick::Real, [description = "Pitch rate the stick asks for (deg/s)"]
        nz_cmd::Real, [description = "Load factor the stick asks for, turn compensation included (g)"]
        lim_active::Real, [description = "1 while the alpha/g limiter cuts the command, else 0"]
    end
    @parameters begin
        g0::Real = 9.80665, [unit = "m/s^2", description = "Gravity"]
        nz_pull::Real = 10.0, [description = "Load factor per unit aft stick (g)"]
        nz_push::Real = 4.0, [description = "Load factor per unit forward stick (g)"]
        limiter::Real = 1.0, [description = "1: limiter on, 0: off"]
        turn_comp::Real = 1.0, [description = "1: turn compensation on, 0: off"]
        alpha_max::Real = 25.0, [description = "Alpha limit (deg)"]
        nz_max::Real = 9.0, [description = "Load-factor limit (g)"]
        nz_min::Real = -3.0, [description = "Negative load-factor limit (g)"]
        k_alim::Real = 3.0, [description = "Alpha-limiter gain ((deg/s)/deg)"]
        k_glim::Real = 4.0, [description = "g-limiter gain ((deg/s)/g)"]
        k_nzc::Real = 2.0, [description = "g-error feedback of the command, in units of g0/vt"]
        nzc_lim::Real = 0.5, [description = "Clamp of the g error in that feedback (g)"]
    end
    @variables begin
        cphi::Real = 1.0, [description = "cos(phi)"]
        cg::Real = 1.0, [description = "cos(gamma) cos(phi): the 1 g of a level pull-up"]
        tc::Real = 0.0, [description = "Turn compensation (g)"]
        kq::Real = 1.0, [description = "g0/vt in deg/s per g"]
        dn_cmd::Real = 0.0, [description = "Load factor asked for above the path's 1 g"]
        dn::Real = 0.0, [description = "Load factor above the 1 g of straight flight"]
        q_alpha::Real = 0.0, [description = "Alpha-limiter ceiling (deg/s)"]
        q_g::Real = 0.0, [description = "g-limiter ceiling (deg/s)"]
        q_neg::Real = 0.0, [description = "Negative-g floor (deg/s)"]
        q_lim::Real = 0.0, [description = "The smaller ceiling (deg/s)"]
    end
    @equations begin
        cphi ~ cos(phi)
        cg ~ cos(gamma) * cphi
        tc ~ turn_comp * ifelse(cphi >= 0.5, 1.0 / max(cphi, 0.5) - 1.0, max(2.0 * cphi, 0.0))
        nz_cmd ~ 1.0 + ifelse(stick >= 0.0, nz_pull * stick, nz_push * stick) + tc
        kq ~ g0 / vt * 57.29577951308232
        dn_cmd ~ nz_cmd - cg
        dn ~ nz - cos(theta) * cphi
        q_stick ~ kq * (dn_cmd + k_nzc * clamp(dn_cmd - dn, -nzc_lim, nzc_lim))
        q_alpha ~ k_alim * (alpha_max - alpha)
        q_g ~ kq * (nz_max - cg) + k_glim * (nz_max - nz)
        q_neg ~ kq * (nz_min - cg) + k_glim * (nz_min - nz)
        q_lim ~ min(q_alpha, q_g)
        q_cmd ~ ifelse(limiter > 0.5, max(min(q_stick, q_lim), q_neg), q_stick)
        lim_active ~ ifelse(limiter > 0.5, ifelse(q_stick > q_lim, 1.0, 0.0), 0.0)
    end
end
