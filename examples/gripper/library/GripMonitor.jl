@block GripMonitor begin
    # Grip analysis of a part held by friction between two parallel jaws (a sensor, not physics).
    #
    # Required friction: to move with the carriage the part needs the force m (a - g_vec) from
    # the jaws, a = carriage acceleration, g_vec = (0, 0, -g0); with the jaw normal along x and
    # the motion in y and z, all of it is friction:
    #   need   = m sqrt(a_x^2 + a_y^2 + (g0 + a_z)^2)
    # Two jaws with the grip (normal) force F each carry at most 2 mu F, so the grip force must be
    #   F_req  = (need + kM m a_h) / (2 mu)   (S = 1),   F_reqS = S F_req   (the sizing rule)
    # The kM term is the tilting moment of a part whose centre of mass hangs ez below the grip
    # line: M = m a_h ez about the jaw axis, carried by friction at a torsion lever r_t of the pad
    # contact points, |F_t| + M / r_t <= 2 mu F, so kM = ez / r_t (0 for the ball).
    # The monitor compares that requirement with what the contacts do:
    #   demand = |tangential part of FA + FB|  (the friction the two jaw contacts deliver)
    #   cap    = mu (fnA + fnB)               (their friction capacity)
    #   S_act  = cap / need                   (the safety factor in effect)
    # The part's position relative to the gripping point (the carriage origin) gives the slip
    # distance `slipd` (in the jaw plane y-z). `holds` drops to 0 (latched) the first time the
    # slip distance exceeds d_hold while the part is gripped; `F_slip` and `t_slip` latch the grip
    # force and the time at the first instant the mean slip speed exceeds s_th while gripped.
    @inputs begin
        g::Vec{7}, [description = "Part pose (centre of mass)"]
        pc::Vec{3}, [unit = "m", description = "Carriage (gripping point) position"]
        ac::Vec{3}, [unit = "m/s^2", description = "Carriage acceleration"]
        FA::Vec{3}, [unit = "N", description = "World force of jaw A on the part"]
        FB::Vec{3}, [unit = "N", description = "World force of jaw B on the part"]
        fnA::Real, [unit = "N", description = "Normal force of jaw A"]
        fnB::Real, [unit = "N", description = "Normal force of jaw B"]
        slipA::Real, [unit = "m/s", description = "Slip speed at jaw A"]
        slipB::Real, [unit = "m/s", description = "Slip speed at jaw B"]
        cmd::Real, [unit = "1", description = "Gripper command (1 closed): the part counts as gripped only while it is 1"]
    end
    @outputs begin
        F_grip::Real, [unit = "N", description = "Grip force: mean normal force of the two jaws"]
        need::Real, [unit = "N", description = "Friction the part needs to follow the carriage, m |a - g|"]
        demand::Real, [unit = "N", description = "Friction delivered by the jaw contacts, |tangential (FA + FB)|"]
        cap::Real, [unit = "N", description = "Friction capacity mu (fnA + fnB)"]
        F_req::Real, [unit = "N", description = "Required grip force per jaw, S = 1"]
        F_reqS::Real, [unit = "N", description = "Required grip force per jaw with the safety factor S"]
        a_h::Real, [unit = "m/s^2", description = "Horizontal carriage acceleration |(a_x, a_y)|"]
        tilt::Real, [unit = "rad", description = "Part rotation about the jaw axis x (the tilt in the grip)"]
        S_act::Real, [unit = "1", description = "Safety factor in effect, cap / need"]
        dx::Real, [unit = "m", description = "Part position relative to the gripping point, x"]
        dy::Real, [unit = "m", description = "Part position relative to the gripping point, y"]
        dz::Real, [unit = "m", description = "Part position relative to the gripping point, z"]
        slipd::Real, [unit = "m", description = "Slip distance in the jaw plane, sqrt(dy^2 + dz^2)"]
        slipv::Real, [unit = "m/s", description = "Mean slip speed of the two jaw contacts"]
        gripped::Real, [unit = "1", description = "1 while the part is gripped: commanded closed and F_grip above Fg0 (smooth)"]
        holds::Real, [unit = "1", description = "1 while the part holds; latched to 0 at the first slip beyond d_hold"]
        F_slip::Real, [unit = "N", description = "Grip force at the first slip (slip speed above s_th), or 0"]
        t_slip::Real, [unit = "s", description = "Time of the first slip, or 0"]
    end
    @parameters begin
        m::Real = 0.5, [unit = "kg", min = 0, description = "Part mass"]
        mu::Real = 0.25, [unit = "1", min = 1.0e-6, description = "Jaw friction coefficient"]
        S::Real = 2.0, [unit = "1", min = 0, description = "Safety factor of the sizing rule"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        d_hold::Real = 0.002, [unit = "m", min = 0, description = "Slip distance that counts as lost"]
        s_th::Real = 0.01, [unit = "m/s", min = 0, description = "Slip speed that counts as sliding"]
        Fg0::Real = 2.0, [unit = "N", min = 1.0e-9, description = "Grip force above which the part counts as gripped"]
        ez::Real = 0.0, [unit = "m", description = "Centre of mass below the grip line (the gripping point)"]
        kM::Real = 0.0, [unit = "1", min = 0, description = "Moment term of the requirement, ez / r_t (0: no tilting moment)"]
    end
    @variables begin
        lost::Real = 0.0, [unit = "1", description = "Held: 1 after the part was lost"]
        nsl::Real = 0.0, [unit = "1", description = "Held: number of slip-speed events"]
        Fs::Real = 0.0, [unit = "N", description = "Held: grip force at the first slip"]
        ts::Real = 0.0, [unit = "s", description = "Held: time of the first slip"]
        Ft2::Real = 0.0, [unit = "N", description = "Jaw friction, world y"]
        Ft3::Real = 0.0, [unit = "N", description = "Jaw friction, world z"]
    end
    @equations begin
        F_grip ~ 0.5 * (fnA + fnB)
        need ~ m * sqrt(ac[1] * ac[1] + ac[2] * ac[2] + (g0 + ac[3]) * (g0 + ac[3]))
        Ft2 ~ FA[2] + FB[2]
        Ft3 ~ FA[3] + FB[3]
        demand ~ sqrt(Ft2 * Ft2 + Ft3 * Ft3)
        cap ~ mu * (fnA + fnB)
        a_h ~ sqrt(ac[1] * ac[1] + ac[2] * ac[2] + 1.0e-12)
        F_req ~ (need + kM * m * a_h) / (2 * mu)
        F_reqS ~ S * F_req
        S_act ~ cap / need
        dx ~ g[5] - pc[1]
        dy ~ g[6] - pc[2]
        dz ~ g[7] - pc[3] + ez
        tilt ~ 2 * atan(g[2] / g[1])
        slipd ~ sqrt(dy * dy + dz * dz)
        slipv ~ 0.5 * (slipA + slipB)
        gripped ~ cmd * 0.5 * (1 + tanh((F_grip - Fg0) / (0.2 * Fg0)))
        ddt(lost) ~ 0.0
        ddt(nsl) ~ 0.0
        ddt(Fs) ~ 0.0
        ddt(ts) ~ 0.0
        holds ~ 1 - lost
        F_slip ~ Fs
        t_slip ~ ts
    end
    @events begin
        slipd * gripped - d_hold > 0.0 => begin
            reinit(lost, 1.0)
        end
        slipv * gripped - s_th > 0.0 => begin
            reinit(Fs, ifelse(nsl < 0.5, F_grip, Fs))
            reinit(ts, ifelse(nsl < 0.5, t, ts))
            reinit(nsl, nsl + 1.0)
        end
    end
end
