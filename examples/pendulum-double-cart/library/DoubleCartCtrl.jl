@block DoubleCartCtrl begin
    # Firmware of the cart pendulum, 1 kHz. Three phases, latched in `mode`:
    #   0  hold: the motor voltage is 0 until t_on (the pendulum hangs at rest).
    #   1  swing-up from t_on: u = u_ff(tau) - K(tau) (z - z*(tau)), tau = t - t_on. The feed-forward voltage u_ff,
    #      the nominal state z* and the time-varying LQR gain K come from the offline trajectory optimisation;
    #      the block `DoubleCartTraj` looks them up in 10 ms tables and this block samples them at every tick.
    #   2  balance from tau >= T_s (the nominal ends upright, at rest): u = -K_lqr z, the discrete
    #      infinite-horizon LQR of the 1 ms sampled linearisation at the upright.
    # z = [x, th_1, th_2, v, w_1, w_2] with the absolute link angles th_i from the upward vertical and their
    # rates w_i (sums of the joint encoder angles and rates). The output is clamped to +-u_max.
    # design/design.py writes the gains: do not edit them by hand.
    @inputs begin
        tm::Real, [unit = "s"]
        x::Real, [unit = "m"]
        v::Real, [unit = "m/s"]
        q1::Real, [unit = "rad"]
        q2::Real, [unit = "rad"]
        wq1::Real, [unit = "rad/s"]
        wq2::Real, [unit = "rad/s"]
        ff::Real, [unit = "V"]
        xs::Vec{6}
        Ks::Vec{6}
    end
    @outputs begin
        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage"]
        phase::Real = 0.0, [description = "0 hold, 1 swing-up (TVLQR), 2 balance (LQR)"]
        th1::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 1 from the upward vertical"]
        th2::Real = -3.1415926535897931, [unit = "rad", description = "Absolute angle of link 2 from the upward vertical"]
    end
    @parameters begin
        t_on::Real = 1, [unit = "s", description = "Start of the swing-up"]
        T_s::Real = 2.4, [unit = "s", description = "Swing-up duration (the catch follows at t_on + T_s)"]
        u_max::Real = 24, [unit = "V", min = 0, description = "Voltage limit"]
        Klqr::Vec{6} = [30.0509285, 128.115493, -257.959052, 23.9559011, -7.47878546, -26.3963107], [description = "LQR gain on [x, th1, th2, v, w1, w2] (u = -K z)"]
    end
    @variables begin
        mode::Real = 0.0, [description = "Latched phase"]
    end
    @discrete Ts = 0.001 begin
        t1 = q1 - 1.5707963267948966
        t2 = t1 + q2
        w1a = wq1
        w2a = w1a + wq2
        th1 = t1
        th2 = t2
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
            out = -(Klqr[1] * x + Klqr[2] * t1 + Klqr[3] * t2 + Klqr[4] * v + Klqr[5] * w1a + Klqr[6] * w2a)
        end
        if mode > 0.5 && mode < 1.5
            out = ff - (Ks[1] * (x - xs[1]) + Ks[2] * (t1 - xs[2]) + Ks[3] * (t2 - xs[3]) + Ks[4] * (v - xs[4]) + Ks[5] * (w1a - xs[5]) + Ks[6] * (w2a - xs[6]))
        end
        u = clamp(out, -u_max, u_max)
        phase = mode
    end
end
