@block PosCtrl begin
    # 50 Hz outer loops, PX4 style, for a vehicle that has **no yaw actuator**:
    #
    #   v_cmd = clamp(Kp (p_sp - p) + v_sp)                       (P on position, speed limits)
    #   a_cmd = a_sp + k_drag v_sp + Kv (v_cmd - v) + Ki int(v_cmd - v) - Kd dv/dt
    #   z_d  ~ (a_x, a_y, g)                                      (thrust direction, as PX4)
    #   F_z  = m_nom (a_z + g),   F_vec = F_z (a_x / g, a_y / g, 1)
    #
    # The tilt is a_h/g, limited to `tilt_max`. The vertical integral is left out of the
    # direction on purpose: it learns thrust losses that turn with the body (the fins' download
    # in the slipstream, a mass error), and with such a loss the net force still tilts by a_h/g;
    # dividing by g + Ki-term would make the horizontal response a few percent too weak. The
    # collective thrust F = F_vec . (R(q) e_z) is what the rotor has to produce, and the desired
    # attitude has body z along F_vec. The heading of the desired attitude is the **measured** heading `psi`, not
    # a commanded one: a single propeller cannot yaw, so the position controller expresses its
    # roll/pitch demand in whatever heading the fins have left the body at, and the heading
    # itself is never controlled.
    #
    # `k_drag v_sp` (horizontal) feeds forward the airframe's linear drag: the fins in the
    # slipstream resist a lateral velocity like a damper (`design.py` derives k_drag).
    #
    # The mission's jerk `j_sp` is fed forward as a tilt-rate set-point: the thrust direction
    # turns at j/g, which in the heading frame (x_h, y_h) is a pitch rate j_xh/g and a roll rate
    # -j_yh/g (`w_ff`, scaled with the tilt limit). Without it the acceleration feed-forward
    # reaches the body only through the lag of the attitude loop.
    #
    # Ground contact (`contact` from `Waypoints`, latched at the touchdown): the loops stop
    # flying. The integrators are frozen, the desired attitude is level in the measured
    # heading, and the vertical channel no longer reacts to the measured motion: the rebound of
    # the feet would otherwise read as a climb, cut the thrust and slow the rotor while the body
    # is in the air, and the rotor's lost angular momentum would go into the body's yaw. The
    # collective thrust is the value of the last tick before the touchdown times the mission's
    # fraction `thr` (1 while the hop settles, then smoothly to 0); the drive caps the rotor
    # speed below it (`RotorEsc`).
    @inputs begin
        p::Vec{3}
        v::Vec{3}
        q::Vec{4}
        p_sp::Vec{3}
        v_sp::Vec{3}
        a_sp::Vec{3}
        j_sp::Vec{3}
        psi::Real
        armed::Real
        contact::Real, [description = "1 from the touchdown latch: hold the thrust, level attitude"]
        thr::Real, [description = "Fraction of the touchdown thrust kept on the ground"]
    end
    @outputs begin
        qd::Vec{4} = [1.0, 0.0, 0.0, 0.0]
        F::Real = 0.0, [unit = "N", description = "Collective thrust command"]
        a_cmd::Vec{3} = [0.0, 0.0, 0.0]
        w_ff::Vec{2} = [0.0, 0.0], [unit = "rad/s", description = "Tilt-rate feed-forward (roll, pitch)"]
    end
    @parameters begin
        m_nom::Real = 1.14, [unit = "kg", min = 0, description = "Nominal mass of the thrust feedforward"]
        g0::Real = 9.81, [unit = "m/s^2"]
        Kp_xy::Real = 1.0, [unit = "1/s", description = "Horizontal position gain"]
        Kp_z::Real = 1.5, [unit = "1/s", description = "Vertical position gain"]
        Kv_xy::Real = 3.0, [unit = "1/s", description = "Horizontal velocity P gain"]
        Kv_z::Real = 5.0, [unit = "1/s", description = "Vertical velocity P gain"]
        Ki_xy::Real = 1.2, [unit = "1/s^2", description = "Horizontal velocity I gain"]
        Ki_z::Real = 2.0, [unit = "1/s^2", description = "Vertical velocity I gain"]
        Kd_xy::Real = 0.08, [description = "Horizontal velocity D gain (on the measurement)"]
        Kd_z::Real = 0.10, [description = "Vertical velocity D gain (on the measurement)"]
        k_drag::Real = 0.0, [unit = "1/s", description = "Horizontal drag feed-forward (drag per unit mass and speed)"]
        d_alpha::Real = 0.4, [description = "First-order filter factor of the D term per tick"]
        i_max_xy::Real = 2.0, [unit = "m/s^2", description = "Horizontal integral limit"]
        i_max_z::Real = 3.0, [unit = "m/s^2", description = "Vertical integral limit"]
        v_max_xy::Real = 1.6, [unit = "m/s", description = "Horizontal speed limit"]
        v_up::Real = 1.0, [unit = "m/s", description = "Climb speed limit"]
        v_down::Real = 0.8, [unit = "m/s", description = "Descent speed limit"]
        tilt_max::Real = 0.24, [unit = "rad", description = "Tilt limit of the thrust vector"]
        F_max::Real = 25.0, [unit = "N", description = "Collective thrust limit"]
    end
    @variables begin
        iv::Vec{3} = [0.0, 0.0, 0.0], [description = "Velocity integral (acceleration)"]
        vprev::Vec{3} = [0.0, 0.0, 0.0], [description = "Velocity of the previous tick"]
        dfilt::Vec{3} = [0.0, 0.0, 0.0], [description = "Filtered velocity derivative"]
        F_td::Real = 0.0, [unit = "N", description = "Collective thrust held from the touchdown"]
        lat::Real = 0.0, [description = "Touchdown latch of F_td"]
    end
    @discrete Ts = 20e-3 begin
        ep = p_sp - p
        vx = Kp_xy * ep[1] + v_sp[1]
        vy = Kp_xy * ep[2] + v_sp[2]
        vz = clamp(Kp_z * ep[3] + v_sp[3], -v_down, v_up)
        sh = min(1.0, v_max_xy / max(sqrt(vx * vx + vy * vy), 1.0e-6))
        ev = [vx * sh - v[1], vy * sh - v[2], vz - v[3]]
        dm = (v - vprev) / Ts
        dfilt = dfilt + d_alpha * (dm - dfilt)
        vprev = v
        gc = ifelse(contact > 0.5, 1.0, 0.0)
        if lat < 0.5 && gc > 0.5
            # F still holds the last tick before the touchdown
            F_td = F
            lat = 1.0
        end
        if armed > 0.5
            # frozen in ground contact
            iv = [
                clamp(iv[1] + (1.0 - gc) * Ki_xy * ev[1] * Ts, -i_max_xy, i_max_xy),
                clamp(iv[2] + (1.0 - gc) * Ki_xy * ev[2] * Ts, -i_max_xy, i_max_xy),
                clamp(iv[3] + (1.0 - gc) * Ki_z * ev[3] * Ts, -i_max_z, i_max_z)
            ]
        else
            iv = [0.0, 0.0, 0.0]
        end
        ac = [
            Kv_xy * ev[1] + iv[1] - Kd_xy * dfilt[1] + a_sp[1] + k_drag * v_sp[1],
            Kv_xy * ev[2] + iv[2] - Kd_xy * dfilt[2] + a_sp[2] + k_drag * v_sp[2],
            Kv_z * ev[3] + iv[3] - Kd_z * dfilt[3] + a_sp[3]
        ]
        fz = max(m_nom * (ac[3] + g0), 0.3 * m_nom * g0)
        ah = sqrt(ac[1] * ac[1] + ac[2] * ac[2])
        sc = min(1.0, g0 * tan(tilt_max) / max(ah, 1.0e-9))
        Fv = [(1.0 - gc) * fz * ac[1] * sc / g0, (1.0 - gc) * fz * ac[2] * sc / g0, fz]
        zd = Fv / norm(Fv)
        zb = [
            2 * (q[2] * q[4] + q[1] * q[3]),
            2 * (q[3] * q[4] - q[1] * q[2]),
            q[1] * q[1] - q[2] * q[2] - q[3] * q[3] + q[4] * q[4]
        ]
        xc = [cos(psi), sin(psi), 0.0]
        yd0 = cross(zd, xc)
        yd = yd0 / norm(yd0)
        xd = cross(yd, zd)
        w4 = 0.5 * sqrt(max(1.0 + xd[1] + yd[2] + zd[3], 1.0e-6))
        jx = cos(psi) * j_sp[1] + sin(psi) * j_sp[2]
        jy = -sin(psi) * j_sp[1] + cos(psi) * j_sp[2]
        if armed > 0.5
            Fl = clamp(dot(Fv, zb), 0.0, F_max)
            F = ifelse(gc > 0.5, F_td * thr, Fl)
            qd = [w4, (yd[3] - zd[2]) / (4 * w4), (zd[1] - xd[3]) / (4 * w4), (xd[2] - yd[1]) / (4 * w4)]
            w_ff = [-(1.0 - gc) * sc * jy / g0, (1.0 - gc) * sc * jx / g0]
        else
            F = 0.0
            qd = [1.0, 0.0, 0.0, 0.0]
            w_ff = [0.0, 0.0]
        end
        a_cmd = ac
    end
end
