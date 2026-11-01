@block CupTool begin
    # The robot tool that carries the cup, as a prescribed motion. The tool frame T is the cup
    # mount (z up; the cup hangs along -z). It is turned by `th` about the world y axis through
    # the mount and moves in the world x-z plane:
    #
    #   R_T = Ry(th),  p_T = (x, 0, z),   pose g = (cos(th/2), 0, sin(th/2), 0, x, 0, z),
    #   body twist tw = (0, th', 0, cos(th) x' - sin(th) z', 0, sin(th) x' + cos(th) z').
    #
    # The vertical pick-lift-lower-retract comes from three S-curve profiles (inputs zv1..zv3);
    # on top of it one excitation, chosen by `motion`, starts at t_x0:
    #   1 hold        nothing (the tool hangs still);
    #   2 bounce      a quick step down by A_st in T_st (the axial mode rings down for T_ring),
    #                 then a vertical chirp, f0..f1 in T_c, amplitude rising from a0 A_c to A_c;
    #   3 steps       three horizontal moves along x with acceleration pulses of a_s/3, 2a_s/3,
    #                 a_s (duration T_p, rise time ~2 tau_s), coasting T_c, alternating direction;
    #   4 swing       a quasi-static tilt to th_A and back (T_sw each way, held T_h), then
    #                 N_sw cycles of +-th_B at f_sw;
    #   5 chirp       a lateral (x) chirp, f0..f1 in T_c, amplitude rising from a0 A_c to A_c.
    # Smooth steps are U(t) = (1 + tanh(t/w))/2, so no events; the chirps fade in and out over
    # T_env. The chirp's phase, amplitude and frequency are outputs for the transmissibility
    # demodulator. The tool position and tilt are states integrated from the velocities.
    @inputs begin
        zv1::Real, [unit = "m/s", description = "Lift profile velocity"]
        za1::Real, [unit = "m/s^2", description = "Lift profile acceleration"]
        zv2::Real, [unit = "m/s", description = "Lower profile velocity"]
        za2::Real, [unit = "m/s^2", description = "Lower profile acceleration"]
        zv3::Real, [unit = "m/s", description = "Retract profile velocity"]
        za3::Real, [unit = "m/s^2", description = "Retract profile acceleration"]
    end
    @parameters begin
        motion::Real = 1.0, [unit = "1", min = 1, max = 5, description = "1 hold, 2 bounce, 3 horizontal steps, 4 tilt swing, 5 lateral chirp"]
        t_x0::Real = 1.0, [unit = "s", description = "Start of the excitation"]
        A_st::Real = 0.004, [unit = "m", description = "Bounce: step down"]
        T_st::Real = 0.04, [unit = "s", min = 1.0e-4, description = "Bounce: step duration"]
        T_ring::Real = 0.8, [unit = "s", description = "Bounce: ring-down time before the chirp"]
        A_z::Real = 1.5e-3, [unit = "m", description = "Bounce: chirp amplitude (end)"]
        f0_z::Real = 3.0, [unit = "Hz", description = "Bounce: chirp start frequency"]
        f1_z::Real = 20.0, [unit = "Hz", description = "Bounce: chirp end frequency"]
        T_cz::Real = 5.0, [unit = "s", min = 1.0e-3, description = "Bounce: chirp duration"]
        a_s::Real = 6.0, [unit = "m/s^2", description = "Steps: largest acceleration"]
        T_p::Real = 0.15, [unit = "s", description = "Steps: acceleration pulse duration"]
        T_c::Real = 0.6, [unit = "s", description = "Steps: coast (and pause) duration"]
        tau_s::Real = 0.008, [unit = "s", min = 1.0e-5, description = "Steps: rise time scale of a pulse edge"]
        th_A::Real = 80.0, [unit = "1", description = "Swing: quasi-static tilt, degrees"]
        T_sw::Real = 0.8, [unit = "s", min = 1.0e-3, description = "Swing: duration of the tilt and of the return"]
        T_h::Real = 0.6, [unit = "s", description = "Swing: hold at th_A"]
        th_B::Real = 25.0, [unit = "1", description = "Swing: amplitude of the fast swing, degrees"]
        f_sw::Real = 2.0, [unit = "Hz", min = 1.0e-3, description = "Swing: frequency of the fast swing"]
        N_sw::Real = 3.0, [unit = "1", description = "Swing: cycles of the fast swing"]
        w_o::Real = 0.05, [unit = "s", min = 1.0e-4, description = "Swing: edge width of the fast swing envelope"]
        A_x::Real = 4.0e-4, [unit = "m", description = "Chirp: lateral amplitude (end)"]
        f0_x::Real = 1.5, [unit = "Hz", description = "Chirp: start frequency"]
        f1_x::Real = 20.0, [unit = "Hz", description = "Chirp: end frequency"]
        T_cx::Real = 10.0, [unit = "s", min = 1.0e-3, description = "Chirp: duration"]
        a0::Real = 0.3, [unit = "1", description = "Chirps: start amplitude as a share of the end amplitude"]
        T_env::Real = 0.25, [unit = "s", min = 1.0e-3, description = "Chirps: fade-in and fade-out time"]
    end
    @variables begin
        x::Real = 0.0, [unit = "m", state = :prefer, description = "Tool x"]
        z::Real = 0.07, [unit = "m", state = :prefer, description = "Tool z"]
        th::Real = 0.0, [unit = "rad", state = :prefer, description = "Tool tilt about world y"]
        vxs::Real = 0.0, [unit = "m/s", state = :prefer, description = "Tool x velocity of the step moves"]
        w2::Real = 0.0, [unit = "1", description = "Weight of the bounce"]
        w3::Real = 0.0, [unit = "1", description = "Weight of the steps"]
        w4::Real = 0.0, [unit = "1", description = "Weight of the swing"]
        w5::Real = 0.0, [unit = "1", description = "Weight of the lateral chirp"]
        # steps: pulses of moves 1..3 (a: accelerate, d: decelerate)
        t1::Real = 0.0, [unit = "s", description = "Start of move 1"]
        t2::Real = 0.0, [unit = "s", description = "Start of move 2"]
        t3::Real = 0.0, [unit = "s", description = "Start of move 3"]
        p1a::Real = 0.0, [unit = "1"]
        p1d::Real = 0.0, [unit = "1"]
        p2a::Real = 0.0, [unit = "1"]
        p2d::Real = 0.0, [unit = "1"]
        p3a::Real = 0.0, [unit = "1"]
        p3d::Real = 0.0, [unit = "1"]
        axs::Real = 0.0, [unit = "m/s^2", description = "Tool x acceleration of the step moves"]
        # bounce step
        wst::Real = 0.01, [unit = "s", description = "Edge width of the bounce step"]
        vst::Real = 0.0, [unit = "m/s", description = "Tool z velocity of the bounce step"]
        # chirp (shared by the bounce and the lateral chirp)
        tc0::Real = 0.0, [unit = "s", description = "Chirp start"]
        Tc::Real = 1.0, [unit = "s", description = "Chirp duration"]
        Ac::Real = 0.0, [unit = "m", description = "Chirp end amplitude"]
        f0::Real = 1.0, [unit = "Hz", description = "Chirp start frequency"]
        f1::Real = 1.0, [unit = "Hz", description = "Chirp end frequency"]
        tau::Real = 0.0, [unit = "s", description = "Time since the chirp start"]
        tin::Real = 0.0, [unit = "1", description = "1 inside the chirp window"]
        tcl::Real = 0.0, [unit = "s", description = "Clamped chirp time"]
        we::Real = 0.1, [unit = "s", description = "Envelope edge width"]
        e1::Real = 0.0, [unit = "1", description = "Fade-in tanh"]
        e2::Real = 0.0, [unit = "1", description = "Fade-out tanh"]
        env::Real = 0.0, [unit = "1", description = "Chirp envelope"]
        envd::Real = 0.0, [unit = "1/s", description = "Envelope rate"]
        ramp::Real = 0.0, [unit = "1", description = "Amplitude ramp a0..1"]
        rampd::Real = 0.0, [unit = "1/s", description = "Ramp rate"]
        Am::Real = 0.0, [unit = "m", description = "Chirp amplitude"]
        Amd::Real = 0.0, [unit = "m/s", description = "Chirp amplitude rate"]
        ph::Real = 0.0, [unit = "rad", description = "Chirp phase"]
        phd::Real = 0.0, [unit = "rad/s", description = "Chirp phase rate"]
        vc::Real = 0.0, [unit = "m/s", description = "Chirp velocity"]
        # swing
        ws::Real = 0.1, [unit = "s", description = "Edge width of the quasi-static swing"]
        q1::Real = 0.0, [unit = "1"]
        q2::Real = 0.0, [unit = "1"]
        to::Real = 0.0, [unit = "s", description = "Start of the fast swing"]
        Tosc::Real = 1.0, [unit = "s", description = "Duration of the fast swing"]
        o1::Real = 0.0, [unit = "1"]
        o2::Real = 0.0, [unit = "1"]
        eo::Real = 0.0, [unit = "1", description = "Fast swing envelope"]
        eod::Real = 0.0, [unit = "1/s", description = "Fast swing envelope rate"]
        pso::Real = 0.0, [unit = "rad", description = "Fast swing phase"]
        thd::Real = 0.0, [unit = "rad/s", description = "Tilt rate"]
        vx::Real = 0.0, [unit = "m/s", description = "Tool x velocity"]
        vz::Real = 0.0, [unit = "m/s", description = "Tool z velocity"]
        cth::Real = 1.0, [unit = "1", description = "cos(th)"]
        sth::Real = 0.0, [unit = "1", description = "sin(th)"]
    end
    @outputs begin
        g::Vec{7}
        tw::Vec{6}
        theta::Real, [unit = "1", description = "Tool tilt, degrees"]
        ax::Real, [unit = "m/s^2", description = "Tool x acceleration of the step moves"]
        az::Real, [unit = "m/s^2", description = "Tool z acceleration of the lift, lower and retract"]
        xc::Real, [unit = "m", description = "Chirp displacement A sin(phase)"]
        sp::Real, [unit = "1", description = "sin of the chirp phase"]
        cp::Real, [unit = "1", description = "cos of the chirp phase"]
        A::Real, [unit = "m", description = "Chirp amplitude (envelope included)"]
        f::Real, [unit = "Hz", description = "Instantaneous chirp frequency (0 outside the chirp)"]
    end
    @equations begin
        w2 ~ ifelse(abs(motion - 2) < 0.5, 1.0, 0.0)
        w3 ~ ifelse(abs(motion - 3) < 0.5, 1.0, 0.0)
        w4 ~ ifelse(abs(motion - 4) < 0.5, 1.0, 0.0)
        w5 ~ ifelse(abs(motion - 5) < 0.5, 1.0, 0.0)
        # ---------------------------------------------------------- 3: horizontal steps
        t1 ~ t_x0
        t2 ~ t_x0 + 2 * T_p + 2 * T_c
        t3 ~ t_x0 + 4 * T_p + 4 * T_c
        p1a ~ 0.5 * (tanh((t - t1) / tau_s) - tanh((t - t1 - T_p) / tau_s))
        p1d ~ 0.5 * (tanh((t - t1 - T_p - T_c) / tau_s) - tanh((t - t1 - 2 * T_p - T_c) / tau_s))
        p2a ~ 0.5 * (tanh((t - t2) / tau_s) - tanh((t - t2 - T_p) / tau_s))
        p2d ~ 0.5 * (tanh((t - t2 - T_p - T_c) / tau_s) - tanh((t - t2 - 2 * T_p - T_c) / tau_s))
        p3a ~ 0.5 * (tanh((t - t3) / tau_s) - tanh((t - t3 - T_p) / tau_s))
        p3d ~ 0.5 * (tanh((t - t3 - T_p - T_c) / tau_s) - tanh((t - t3 - 2 * T_p - T_c) / tau_s))
        axs ~ w3 * a_s * ((p1a - p1d) / 3 - 2 * (p2a - p2d) / 3 + (p3a - p3d))
        ddt(vxs) ~ axs
        # ---------------------------------------------------------- 2: bounce step
        wst ~ T_st / 4
        vst ~ -w2 * A_st / T_st * 0.5 * (tanh((t - t_x0) / wst) - tanh((t - t_x0 - T_st) / wst))
        # ---------------------------------------------------------- chirps (2 vertical, 5 lateral)
        tc0 ~ t_x0 + w2 * T_ring
        Tc ~ w2 * T_cz + (1 - w2) * T_cx
        Ac ~ w2 * A_z + w5 * A_x
        f0 ~ w2 * f0_z + (1 - w2) * f0_x
        f1 ~ w2 * f1_z + (1 - w2) * f1_x
        tau ~ t - tc0
        tin ~ ifelse(tau < 0.0, 0.0, ifelse(tau > Tc, 0.0, 1.0))
        tcl ~ ifelse(tau < 0.0, 0.0, ifelse(tau > Tc, Tc, tau))
        we ~ T_env / 3
        e1 ~ tanh((tau - T_env) / we)
        e2 ~ tanh((Tc - T_env - tau) / we)
        env ~ 0.25 * (1 + e1) * (1 + e2)
        envd ~ 0.25 * ((1 - e1 * e1) / we * (1 + e2) - (1 + e1) * (1 - e2 * e2) / we)
        ramp ~ a0 + (1 - a0) * tcl / Tc
        rampd ~ tin * (1 - a0) / Tc
        Am ~ Ac * env * ramp
        Amd ~ Ac * (envd * ramp + env * rampd)
        ph ~ 2 * 3.141592653589793 * (f0 * tcl + (f1 - f0) * tcl * tcl / (2 * Tc))
        phd ~ tin * 2 * 3.141592653589793 * (f0 + (f1 - f0) * tcl / Tc)
        vc ~ (w2 + w5) * (Amd * sin(ph) + Am * phd * cos(ph))
        sp ~ sin(ph)
        cp ~ cos(ph)
        A ~ (w2 + w5) * Am
        xc ~ A * sp
        f ~ (w2 + w5) * tin * phd / (2 * 3.141592653589793)
        # ---------------------------------------------------------- 4: swing
        ws ~ T_sw / 6
        q1 ~ tanh((t - t_x0 - T_sw / 2) / ws)
        q2 ~ tanh((t - t_x0 - 1.5 * T_sw - T_h) / ws)
        to ~ t_x0 + 2 * T_sw + T_h + 0.2
        Tosc ~ N_sw / f_sw
        o1 ~ tanh((t - to - 3 * w_o) / w_o)
        o2 ~ tanh((t - to - Tosc + 3 * w_o) / w_o)
        eo ~ 0.5 * (o1 - o2)
        eod ~ 0.5 * ((1 - o1 * o1) - (1 - o2 * o2)) / w_o
        pso ~ 2 * 3.141592653589793 * f_sw * (t - to)
        thd ~ w4 * 3.141592653589793 / 180 * (th_A * 0.5 * ((1 - q1 * q1) - (1 - q2 * q2)) / ws +
                                                th_B * (eod * sin(pso) + eo * 2 * 3.141592653589793 * f_sw * cos(pso)))
        # ---------------------------------------------------------- the tool
        vx ~ vxs + w5 * vc
        vz ~ zv1 + zv2 + zv3 + vst + w2 * vc
        ddt(x) ~ vx
        ddt(z) ~ vz
        ddt(th) ~ thd
        cth ~ cos(th)
        sth ~ sin(th)
        g[1] ~ cos(0.5 * th)
        g[2] ~ 0.0
        g[3] ~ sin(0.5 * th)
        g[4] ~ 0.0
        g[5] ~ x
        g[6] ~ 0.0
        g[7] ~ z
        tw[1] ~ 0.0
        tw[2] ~ thd
        tw[3] ~ 0.0
        tw[4] ~ cth * vx - sth * vz
        tw[5] ~ 0.0
        tw[6] ~ sth * vx + cth * vz
        theta ~ th * 180 / 3.141592653589793
        ax ~ axs
        az ~ za1 + za2 + za3
    end
end
