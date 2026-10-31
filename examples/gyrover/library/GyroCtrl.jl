@block GyroCtrl begin
    # Controllers of the Gyrover, after Tsai, Ferreira and Paredis (IROS 1999, section 4), on
    # the states of the paper (from GyroSense on the bond graph or GyroverRef). All signals use
    # the paper's coordinates and signs.
    #
    # Longitudinal (drive motor, tau1): the paper's state feedback u = K1 x1 on
    # x1 = (theta1, w1, omega0z), shifted to a speed set-point v_ref (wheel rate wr = v_ref / R,
    # pendulum hanging, so x1_ref = (0, -wr, wr)):
    #
    #     tau1 = tau1_max tanh(K1 . (x1 - x1_ref) / tau1_max)
    #
    # Lateral (tilt, through the servo of the paper's eq. 7): u2 = K2 (x2 - x2_ref) on
    # x2 = (theta0, theta2, w2, omega0x, omega0y) is the tilt set-point; the servo reference
    # (r, rd) follows it with bandwidth wc and damping 1/sqrt(2),
    #
    #     rd' = wc^2 (u2 - r) - sqrt(2) wc rd,
    #
    # and a stiff position loop makes the tilt joint follow (r, rd) (the paper models the tilt as
    # that ideal second-order servo):  tau2 = kp_t (r - theta2) + kd_t (rd - w2).
    #
    # Steering (our extension; the paper stabilises about the upright rest only): a heading
    # error asks for a lean, lean_ref = -lean_max tanh(k_psi (psi_ref - psi) / lean_max) (a
    # positive lean turns the rolling robot to negative heading), and
    # x2_ref = (lean_gain lean_ref, 0, 0, 0, yaw_ff) with the steady-turn yaw rate of that lean,
    # yaw_ff = -mgh lean_ref / (Ls + mh v_ref) (the small-angle steady turn of the docs page
    # "Steady turn"). The K2 loop settles at about half the lean it is given (its tilt gain
    # K2[2] = 1.001 leaves the tilt nearly free), so the set-point is pre-scaled by `lean_gain`
    # and the realised lean follows lean_ref. Flywheel: a speed loop tau3 = k_s (w3_ref - w3).
    #
    # `bal` (both balance loops), `lat` (the lateral loop only), `servo`, `spin` and `head` switch
    # the loops on (1) or off (0). The limits are
    # smooth (tanh), so no event is created.
    @parameters begin
        K1::Vec{3} = [-18.44, -3.31, 1.16], [description = "Longitudinal gain (paper), tau1 = K1 x1"]
        K2::Vec{5} = [-0.0077, 1.001, 0.0019, 0.0179, -0.0022], [description = "Lateral gain (paper), u2 = K2 x2"]
        wc::Real = 62.83185307179586, [unit = "rad/s", min = 0, description = "Tilt servo bandwidth (paper: 20 pi)"]
        kp_t::Real = 40000.0, [unit = "N*m/rad", min = 0, description = "Tilt position loop stiffness"]
        kd_t::Real = 20.0, [unit = "N*m*s/rad", min = 0, description = "Tilt position loop damping"]
        k_s::Real = 0.05, [unit = "N*m*s/rad", min = 0, description = "Flywheel speed loop gain"]
        w3_ref::Real = 1570.7963267948965, [unit = "rad/s", description = "Flywheel speed set-point (15 000 rpm)"]
        R::Real = 0.197, [unit = "m", min = 0, description = "Wheel radius"]
        tau1_max::Real = 4.0, [unit = "N*m", min = 0, description = "Drive torque limit"]
        tilt_max::Real = 0.8, [unit = "rad", min = 0, description = "Tilt set-point limit"]
        k_psi::Real = 1.0, [unit = "1", description = "Lean set-point per rad of heading error"]
        lean_max::Real = 0.35, [unit = "rad", min = 0, description = "Lean set-point limit"]
        lean0::Real = 0.0, [unit = "rad", description = "Constant lean set-point (added to the heading loop)"]
        lean_gain::Real = 2.04, [unit = "1", description = "Pre-scale of the lean set-point (inverse steady-state lean gain of the K2 loop)"]
        mgh::Real = 10.43, [unit = "N*m", description = "Gravity moment per lean (m_tot g h)"]
        Ls::Real = 4.73, [unit = "N*m*s", description = "Spin momentum about the axle at rest (flywheel)"]
        mh::Real = 1.08, [unit = "kg*m", description = "Steady-turn speed term per m/s"]
        bal::Real = 1.0, [unit = "1", description = "Balance loops on (1) / off (0)"]
        lat::Real = 1.0, [unit = "1", description = "Lateral loop K2 on (1) / off (0: the tilt is held at 0)"]
        servo::Real = 1.0, [unit = "1", description = "Tilt servo on (1) / off (0)"]
        spin::Real = 1.0, [unit = "1", description = "Flywheel speed loop on (1) / off (0)"]
        head::Real = 0.0, [unit = "1", description = "Heading loop on (1) / off (0)"]
    end
    @inputs begin
        lean::Real
        heading::Real
        th1::Real
        w1::Real
        wz::Real
        th2::Real
        w2::Real
        wx::Real
        wy::Real
        w3::Real
        v_ref::Real
        psi_ref::Real
    end
    @variables begin
        r::Real = 0.0, [unit = "rad", state = :prefer, description = "Tilt servo reference (paper eq. 7)"]
        rd::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Tilt servo reference rate"]
        wr::Real = 0.0, [unit = "rad/s", description = "Wheel-rate set-point"]
        yaw_ff::Real = 0.0, [unit = "rad/s", description = "Steady-turn yaw rate of the lean set-point"]
        a1::Real = 0.0, [unit = "N*m", description = "Unlimited drive torque"]
        a2::Real = 0.0, [unit = "rad", description = "Unlimited tilt set-point"]
    end
    @outputs begin
        tau1::Real, [unit = "N*m", description = "Drive torque (pendulum against wheel)"]
        tau2::Real, [unit = "N*m", description = "Tilt torque (gimbal against pendulum)"]
        tau3::Real, [unit = "N*m", description = "Flywheel torque (rotor against gimbal)"]
        u2::Real, [unit = "rad", description = "Tilt set-point"]
        lean_ref::Real, [unit = "rad", description = "Lean set-point of the heading loop"]
    end
    @equations begin
        wr ~ v_ref / R
        a1 ~ K1[1] * th1 + K1[2] * (w1 + wr) + K1[3] * (wz - wr)
        tau1 ~ bal * tau1_max * tanh(a1 / tau1_max)
        lean_ref ~ lean0 - head * lean_max * tanh(k_psi * (psi_ref - heading) / lean_max)
        yaw_ff ~ -mgh * lean_ref / (Ls + mh * v_ref)
        a2 ~ K2[1] * (lean - lean_gain * lean_ref) + K2[2] * th2 + K2[3] * w2 + K2[4] * wx + K2[5] * (wy - yaw_ff)
        u2 ~ bal * lat * tilt_max * tanh(a2 / tilt_max)
        ddt(r) ~ rd
        ddt(rd) ~ wc * wc * (u2 - r) - 1.4142135623730951 * wc * rd
        tau2 ~ servo * (kp_t * (r - th2) + kd_t * (rd - w2))
        tau3 ~ spin * k_s * (w3_ref - w3)
    end
end
