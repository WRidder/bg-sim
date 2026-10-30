@block TripleCartCtrl begin
    # Firmware of the cart pendulum, 1 kHz. Three phases, latched in `mode`:
    #   0  hold: the motor voltage is 0 until t_on (the pendulum hangs at rest).
    #   1  swing-up from t_on: u = u_ff(tau) - K(tau) (z - z*(tau)), tau = t - t_on. The feed-forward voltage u_ff,
    #      the nominal state z* and the time-varying LQR gain K come from the offline trajectory optimisation;
    #      the block `TripleCartTraj` looks them up in 10 ms tables and this block samples them at every tick.
    #   2  balance from tau >= T_s (the nominal ends upright, at rest): u = -K_lqr z, the discrete
    #      infinite-horizon LQR of the 1 ms sampled linearisation at the upright.
    # z = [x, th_1, th_2, th_3, v, w_1, w_2, w_3] with the absolute link angles th_i from the upward vertical and
    # their rates w_i (sums of the joint encoder angles and rates). The output is clamped to +-u_max.
    # design/design.py writes the gains: do not edit them by hand.
    @inputs begin
        tm::Real, [unit = "s"]
        x::Real, [unit = "m"]
        v::Real, [unit = "m/s"]
        q1::Real, [unit = "rad"]
        q2::Real, [unit = "rad"]
        q3::Real, [unit = "rad"]
        wq1::Real, [unit = "rad/s"]
        wq2::Real, [unit = "rad/s"]
        wq3::Real, [unit = "rad/s"]
        ff::Real, [unit = "V"]
        xs::Vec{8}
        Ks::Vec{8}
    end
    @outputs begin
        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage"]
        phase::Real = 0.0, [description = "0 hold, 1 swing-up (TVLQR), 2 balance (LQR)"]
        th1::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 1 from the upward vertical"]
        th2::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 2 from the upward vertical"]
        th3::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 3 from the upward vertical"]
    end
    @parameters begin
        t_on::Real = 1, [unit = "s", description = "Start of the swing-up"]
        T_s::Real = 3.5, [unit = "s", description = "Swing-up duration (the catch follows at t_on + T_s)"]
        u_max::Real = 24, [unit = "V", min = 0, description = "Voltage limit"]
        Klqr::Vec{8} = [-9.6193149, 102.377612, -440.152539, 428.787496, -19.9490438, 2.10084012, -8.65194868, 38.2300532], [description = "LQR gain on [x, th1, th2, th3, v, w1, w2, w3] (u = -K z)"]
    end
    @variables begin
        mode::Real = 0.0, [description = "Latched phase"]
    end
    @discrete Ts = 0.001 begin
        t1 = q1 - 1.5707963267948966
        t2 = t1 + q2
        t3 = t2 + q3
        w1a = wq1
        w2a = w1a + wq2
        w3a = w2a + wq3
        th1 = t1
        th2 = t2
        th3 = t3
        tau = tm - t_on
        out = 0.0
        if tm >= t_on
            if tau >= T_s
                mode = 2.0
            else
                mode = 1.0
            end
        end
        if mode > 1.5
            out = -(Klqr[1] * x + Klqr[2] * t1 + Klqr[3] * t2 + Klqr[4] * t3 + Klqr[5] * v + Klqr[6] * w1a + Klqr[7] * w2a + Klqr[8] * w3a)
        end
        if mode > 0.5 && mode < 1.5
            out = ff - (Ks[1] * (x - xs[1]) + Ks[2] * (t1 - xs[2]) + Ks[3] * (t2 - xs[3]) + Ks[4] * (t3 - xs[4]) + Ks[5] * (v - xs[5]) + Ks[6] * (w1a - xs[6]) + Ks[7] * (w2a - xs[7]) + Ks[8] * (w3a - xs[8]))
        end
        u = clamp(out, -u_max, u_max)
        phase = mode
    end
end
