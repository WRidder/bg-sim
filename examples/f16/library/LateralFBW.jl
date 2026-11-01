@block LateralFBW begin
    # Lateral-directional fly-by-wire of the f16-sim model: roll-rate command about the velocity
    # vector, yaw damper, aileron-rudder interconnect (ARI) and a sideslip command. Angles in deg,
    # rates in deg/s, surfaces in deg; the gains come in from Lookup2D blocks over (qbar, Mach)
    # and the ARI gain from a Lookup1D over alpha (design/lateral.py).
    #
    #   ps, rs   stability-axis roll and yaw rate (vv_roll = 1): ps = p cos(a) + r sin(a),
    #            rs = r cos(a) - p sin(a). Commanding ps rolls the aircraft about its velocity
    #            vector, so a roll at high alpha does not turn alpha into sideslip. With
    #            vv_roll = 0 the law uses the body rates p, r (a roll about the body x axis).
    #   p_lim    roll-rate limit: p_max clamp(qbar/qbar_full, fq_min, 1) clamp(1 - kn (nz - 1), fn_min, 1)
    #   p_cmd    p_lim * stick (full stick asks for the limit)
    #   ail      Kp (ps - kff p_cmd) + xi_p,     xi_p' = Kip (ps - p_cmd) + (sat(ail) - ail)/t_aw
    #   r_wo     the washed-out yaw rate rs - xw, xw' = r_wo/tau_wo (zero in a steady turn)
    #   rdr      Kari ail + Kr r_wo + Kb (beta - beta_cmd) + xi_b,
    #            xi_b' = Kib (beta - beta_cmd) + (sat(rdr) - rdr)/t_aw,  beta_cmd = -beta_per_pedal pedal
    #
    # The sideslip integral holds beta = beta_cmd, so a turn with the pedals centred is
    # coordinated (beta = 0). Signs of the book: a positive aileron rolls left, a positive rudder
    # yaws left; right pedal yaws the nose right, which is a negative sideslip.
    # The switches roll_law, yaw_damper, beta_hold, ari and vv_roll (1 on, 0 off) take parts of the
    # law out, for the comparisons of the example.
    @inputs begin
        stick::Real, [description = "Roll stick, -1 (full left) .. +1 (full right)"]
        pedal::Real, [description = "Pedals, -1 (full left) .. +1 (full right)"]
        alpha::Real, [description = "Angle of attack (deg)"]
        beta::Real, [description = "Sideslip (deg)"]
        p::Real, [description = "Body roll rate (deg/s)"]
        r::Real, [description = "Body yaw rate (deg/s)"]
        nz::Real, [description = "Load factor (g)"]
        qbar::Real, [unit = "Pa", description = "Dynamic pressure"]
        Kp::Real, [description = "Roll-rate gain (deg per deg/s)"]
        Kip::Real, [description = "Roll-rate integral gain (deg/s per deg/s)"]
        Kr::Real, [description = "Yaw-damper gain (deg per deg/s)"]
        Kb::Real, [description = "Sideslip gain (deg per deg)"]
        Kib::Real, [description = "Sideslip integral gain (deg/s per deg)"]
        Kari::Real, [description = "ARI: rudder per aileron (deg/deg)"]
    end
    @outputs begin
        ail::Real, [description = "Aileron command, limited (deg)"]
        rdr::Real, [description = "Rudder command, limited (deg)"]
        ps::Real, [description = "Stability-axis roll rate (deg/s)"]
        rs::Real, [description = "Stability-axis yaw rate (deg/s)"]
        p_cmd::Real, [description = "Roll-rate command (deg/s)"]
        p_lim::Real, [description = "Roll-rate limit (deg/s)"]
        beta_cmd::Real, [description = "Sideslip command (deg)"]
        r_wo::Real, [description = "Washed-out yaw rate (deg/s)"]
    end
    @parameters begin
        p_max::Real = 240.0, [description = "Roll-rate command at full stick, 1 g, high qbar (deg/s)"]
        qbar_full::Real = 12000.0, [unit = "Pa", min = 1.0, description = "Dynamic pressure from which p_max is available"]
        fq_min::Real = 0.3, [description = "Smallest share of p_max at low qbar"]
        kn::Real = 0.075, [description = "Share of p_max lost per g above 1 g"]
        fn_min::Real = 0.4, [description = "Smallest share of p_max at high g"]
        beta_per_pedal::Real = 6.0, [description = "Sideslip commanded by full pedal (deg)"]
        kff::Real = 0.5, [description = "Share of p_cmd in the proportional path"]
        tau_wo::Real = 1.0, [unit = "s", min = 1.0e-3, description = "Washout time constant"]
        ail_max::Real = 21.5, [description = "Aileron travel (deg)"]
        rdr_max::Real = 30.0, [description = "Rudder travel (deg)"]
        t_aw::Real = 0.1, [unit = "s", min = 1.0e-6, description = "Anti-windup time constant"]
        roll_law::Real = 1.0, [description = "1: roll law on, 0: off (no aileron)"]
        yaw_damper::Real = 1.0, [description = "1: yaw damper on, 0: off"]
        beta_hold::Real = 1.0, [description = "1: sideslip loop on, 0: off"]
        ari::Real = 1.0, [description = "1: aileron-rudder interconnect on, 0: off"]
        vv_roll::Real = 1.0, [description = "1: roll about the velocity vector, 0: about the body x axis"]
    end
    @variables begin
        xi_p::Real = 0.0, [state = :prefer, description = "Roll integrator (deg)"]
        xi_b::Real = 0.0, [state = :prefer, description = "Sideslip integrator (deg)"]
        xw::Real = 0.0, [state = :prefer, description = "Washout state (deg/s)"]
        ca::Real = 1.0, [description = "cos(alpha), or 1 for a body-axis roll"]
        sa::Real = 0.0, [description = "sin(alpha), or 0 for a body-axis roll"]
        fq::Real = 1.0, [description = "Dynamic-pressure share of the roll-rate limit"]
        fn::Real = 1.0, [description = "Load-factor share of the roll-rate limit"]
        ail_raw::Real = 0.0, [description = "Aileron command before the limit (deg)"]
        rdr_raw::Real = 0.0, [description = "Rudder command before the limit (deg)"]
    end
    @equations begin
        ca ~ vv_roll * cos(alpha / 57.29577951308232) + (1.0 - vv_roll)
        sa ~ vv_roll * sin(alpha / 57.29577951308232)
        ps ~ p * ca + r * sa
        rs ~ r * ca - p * sa
        fq ~ clamp(qbar / qbar_full, fq_min, 1.0)
        fn ~ clamp(1.0 - kn * (nz - 1.0), fn_min, 1.0)
        p_lim ~ p_max * fq * fn
        p_cmd ~ p_lim * stick
        ail_raw ~ roll_law * Kp * (ps - kff * p_cmd) + xi_p
        ail ~ clamp(ail_raw, -ail_max, ail_max)
        ddt(xi_p) ~ roll_law * Kip * (ps - p_cmd) + (ail - ail_raw) / t_aw
        beta_cmd ~ -beta_per_pedal * pedal
        r_wo ~ rs - xw
        ddt(xw) ~ r_wo / tau_wo
        rdr_raw ~ ari * Kari * ail + yaw_damper * Kr * r_wo + beta_hold * Kb * (beta - beta_cmd) + xi_b
        rdr ~ clamp(rdr_raw, -rdr_max, rdr_max)
        ddt(xi_b) ~ beta_hold * Kib * (beta - beta_cmd) + (rdr - rdr_raw) / t_aw
    end
end
