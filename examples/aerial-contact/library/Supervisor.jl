@block Supervisor begin
    # The operator script and the discrete phase machine of the switching strategy (paper Fig. 5),
    # 50 Hz. Four phases (output `phase`): 0 free flight, 1 engage, 2 contact, 3 disengage.
    #
    #   0 -> 1  at t >= t_engage, allowed only while the end-effector (wheel plane, estimated from the
    #           navigation filter and the arm angle mu = theta) is within d_guard (30 cm) of the wall;
    #           latches the engage time t_e and the height z_b(t_e) (`z_hold`)
    #   1 -> 2  when the contact is established: the wheel plane has been within d_contact of the wall and the
    #           multirotor has been (nearly) at rest (|v_x| < v_rest) for t_dwell s, i.e. the wall stopped it
    #           (or after t_max_engage s)
    #   2 -> 3  at t >= t_disengage; latches the disengage set-point p_sp = (x_b(t_d) - C, y_b(t_d), z_b(t_d))
    #
    # Free flight: a minimum-jerk move of the position set-point (the "incremental position
    # set-points" of the paper) with exact velocity / acceleration feed-forward. Disengage: the
    # latched fixed set-point (a step). The pitch reference theta_sp ramps from `th0` to `th1` over
    # `T1` s from the engage instant (soft impact), and on to `th2` over `T2` s starting `T2s` s
    # after it (contact). The manipulator set-point is mu_sp = theta_b (arm level) except in contact,
    # where it is mu_c = theta_sp (the arm is level in the world at the equilibrium: design.py).
    # The end-effector velocity command (vy, vz) in [-1, 1] is the open-loop locomotion script
    # (up for t_up, pause t_pause, down for t_down), only issued in the contact phase, with smooth
    # 0.4 s ramps. `a_pos`, `a_rate` arm the position and rate controllers (their integrators are
    # held at zero while another controller is in charge), `sel_eng` and `sel_lqr` select the engage
    # and the contact controller.
    @inputs begin
        tm::Real
        p::Vec{3}
        v::Vec{3}
        q::Vec{4}
    end
    @outputs begin
        phase::Real = 0.0
        p_sp::Vec{3} = [0.45, 0.0, 1.0]
        v_sp::Vec{3} = [0.0, 0.0, 0.0]
        a_sp::Vec{3} = [0.0, 0.0, 0.0]
        psi_sp::Real = 0.0
        theta_sp::Real = 0.0, [unit = "rad"]
        z_hold::Real = 1.0, [unit = "m"]
        mu_sp::Real = 0.0, [unit = "rad"]
        cmd::Vec{2} = [0.0, 0.0]
        a_pos::Real = 1.0
        a_rate::Real = 1.0
        sel_eng::Real = 0.0
        sel_lqr::Real = 0.0
        d_ee::Real = 1.0, [unit = "m"]
    end
    @parameters begin
        p0::Vec{3} = [0.45, 0.0, 1.0], [unit = "m", description = "Hover start position"]
        t_move::Real = 1.5, [unit = "s", description = "Start of the approach move"]
        d_move::Real = 2.5, [unit = "s", min = 0.01, description = "Duration of the approach move"]
        dx_move::Real = 0.25, [unit = "m", description = "x displacement of the approach move"]
        t_engage::Real = 4.5, [unit = "s", description = "Engage request"]
        t_disengage::Real = 28.5, [unit = "s", description = "Disengage request"]
        t_max_engage::Real = 3.0, [unit = "s", description = "Longest engage phase before the contact controller takes over"]
        wall_x::Real = 1.6, [unit = "m", description = "Wall plane"]
        d_guard::Real = 0.30, [unit = "m", description = "Engage is allowed only within this distance of the wall"]
        d_contact::Real = 0.02, [unit = "m", description = "The wheel plane counts as at the wall within this distance"]
        v_rest::Real = 0.1, [unit = "m/s", description = "Speed below which the multirotor counts as stopped by the wall"]
        t_dwell::Real = 0.3, [unit = "s", description = "Time at the wall and at rest before the contact phase starts"]
        C::Real = 0.75, [unit = "m", description = "Disengage back-off distance"]
        L_m::Real = 0.6, [unit = "m", description = "Distance from the multirotor centre of mass to the elastic joint"]
        e_wx::Real = 0.06, [unit = "m", description = "Wheel plane ahead of the elastic joint"]
        th0::Real = 0.20943951023931953, [unit = "rad", description = "theta_sp at the engage instant (12 deg)"]
        th1::Real = 0.3490658503988659, [unit = "rad", description = "theta_sp after the engage ramp (20 deg)"]
        T1::Real = 4.0, [unit = "s", min = 0.01, description = "Engage ramp duration"]
        th2::Real = 0.47123889803846897, [unit = "rad", description = "theta_sp at the end of the contact ramp (27 deg)"]
        T2s::Real = 4.0, [unit = "s", description = "Start of the contact ramp after the engage instant"]
        T2::Real = 3.0, [unit = "s", min = 0.01, description = "Contact ramp duration"]
        t_loc::Real = 13.0, [unit = "s", description = "Start of the ground locomotion"]
        t_up::Real = 6.0, [unit = "s", description = "Up duration"]
        t_pause::Real = 2.0, [unit = "s", description = "Pause duration"]
        t_down::Real = 6.0, [unit = "s", description = "Down duration"]
        v_cmd::Real = 0.125, [description = "Velocity command during locomotion, in [-1, 1]"]
        t_ramp::Real = 0.4, [unit = "s", min = 0.01, description = "Ramp time of the velocity command"]
    end
    @variables begin
        ph::Real = 0.0, [description = "Phase state"]
        t_e::Real = 0.0, [unit = "s", description = "Engage instant"]
        zh::Real = 1.0, [unit = "m", description = "Height latched at the engage instant"]
        dw::Real = 0.0, [unit = "s", description = "Time spent at the wall and at rest"]
        pd::Vec{3} = [0.0, 0.0, 1.0], [unit = "m", description = "Disengage set-point"]
    end
    @discrete Ts = 20e-3 begin
        r11 = 1 - 2 * (q[3] * q[3] + q[4] * q[4])
        r31 = 2 * (q[2] * q[4] - q[1] * q[3])
        r32 = 2 * (q[3] * q[4] + q[1] * q[2])
        r33 = 1 - 2 * (q[2] * q[2] + q[3] * q[3])
        pitch = atan(-r31, hypot(r32, r33))
        # arm vector in the world, x component (arm elevation mu = pitch estimate: level arm)
        r13 = 2 * (q[2] * q[4] + q[1] * q[3])
        ax = L_m * (cos(pitch) * r11 + sin(pitch) * r13)
        dee = wall_x - (p[1] + ax + e_wx)
        ph0 = ph
        if ph0 < 0.5 && tm >= t_engage && dee <= d_guard
            ph = 1.0
            t_e = tm
            zh = p[3]
        end
        dw = ifelse(ph0 > 0.5 && ph0 < 1.5 && dee <= d_contact && abs(v[1]) < v_rest, dw + Ts, 0.0)
        if ph0 > 0.5 && ph0 < 1.5 && (dw >= t_dwell || tm - t_e >= t_max_engage)
            ph = 2.0
        end
        if ph0 > 1.5 && ph0 < 2.5 && tm >= t_disengage
            ph = 3.0
            pd = [p[1] - C, p[2], p[3]]
        end
        sg = clamp((tm - t_move) / d_move, 0.0, 1.0)
        s3 = sg * sg * sg * (10.0 - 15.0 * sg + 6.0 * sg * sg)
        ds = sg * sg * (30.0 - 60.0 * sg + 30.0 * sg * sg) / d_move
        dd = sg * (60.0 - 180.0 * sg + 120.0 * sg * sg) / (d_move * d_move) * ifelse(sg > 0.0 && sg < 1.0, 1.0, 0.0)
        if ph > 2.5
            p_sp = pd
            v_sp = [0.0, 0.0, 0.0]
            a_sp = [0.0, 0.0, 0.0]
        else
            p_sp = p0 + [dx_move * s3, 0.0, 0.0]
            v_sp = [dx_move * ds, 0.0, 0.0]
            a_sp = [dx_move * dd, 0.0, 0.0]
        end
        psi_sp = 0.0
        started = ifelse(ph > 0.5, 1.0, 0.0)
        e1 = started * clamp((tm - t_e) / T1, 0.0, 1.0)
        e2 = started * clamp((tm - t_e - T2s) / T2, 0.0, 1.0)
        theta_sp = th0 + (th1 - th0) * e1 + (th2 - th1) * e2
        z_hold = zh
        mu_sp = ifelse(ph > 1.5 && ph < 2.5, theta_sp, pitch)
        t1 = t_loc + t_up
        t2 = t1 + t_pause
        t3 = t2 + t_down
        ra = clamp((tm - t_loc) / t_ramp, 0.0, 1.0)
        rb = clamp((tm - t1) / t_ramp, 0.0, 1.0)
        rc = clamp((tm - t2) / t_ramp, 0.0, 1.0)
        rd = clamp((tm - t3) / t_ramp, 0.0, 1.0)
        sa = ra * ra * ra * (10.0 - 15.0 * ra + 6.0 * ra * ra)
        sb = rb * rb * rb * (10.0 - 15.0 * rb + 6.0 * rb * rb)
        sc = rc * rc * rc * (10.0 - 15.0 * rc + 6.0 * rc * rc)
        sd = rd * rd * rd * (10.0 - 15.0 * rd + 6.0 * rd * rd)
        vz = v_cmd * (sa - sb - sc + sd)
        cmd = [0.0, ifelse(ph > 1.5 && ph < 2.5, vz, 0.0)]
        phase = ph
        a_pos = ifelse(ph < 0.5 || ph > 2.5, 1.0, 0.0)
        a_rate = ifelse(ph < 1.5 || ph > 2.5, 1.0, 0.0)
        sel_eng = ifelse(ph > 0.5 && ph < 1.5, 1.0, 0.0)
        sel_lqr = ifelse(ph > 1.5 && ph < 2.5, 1.0, 0.0)
        d_ee = dee
    end
end
