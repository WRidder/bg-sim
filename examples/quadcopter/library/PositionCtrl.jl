@block PositionCtrl begin
    # 50 Hz outer loops of the cascade, PX4 style: position P -> velocity PID -> thrust vector
    # -> collective thrust and desired attitude.
    #
    #   v_cmd = clamp(Kp (p_sp - p) + v_sp)             (P on position, velocity feedforward, speed limits)
    #   a_cmd = a_sp + Kv (v_cmd - v) + Ki int(v_cmd - v) - Kd d(v)/dt   (acceleration feedforward, PI on the velocity error, D on the
    #           measurement through a first-order filter; the integral is clamped to +-i_max and frozen
    #           while the block is disarmed, so it carries the mass mismatch and the wind)
    #   F_vec = m_nom (a_cmd + g e_z)                    (gravity feedforward = hover thrust)
    #
    # The horizontal part of F_vec is limited to tilt_max. The outputs are the collective thrust
    # F = F_vec . (R(q) e_z) (the thrust along the body z axis that produces the demanded vertical
    # force, clamped to [0, F_max]) and the desired attitude `qd`: body z along F_vec, body x
    # as close as possible to the heading psi_sp.
    @inputs begin
        p::Vec{3}
        v::Vec{3}
        q::Vec{4}
        p_sp::Vec{3}
        v_sp::Vec{3}
        a_sp::Vec{3}
        psi_sp::Real
        armed::Real
    end
    @outputs begin
        qd::Vec{4} = [1.0, 0.0, 0.0, 0.0]
        F::Real = 0.0, [unit = "N", description = "Collective thrust command"]
        a_cmd::Vec{3} = [0.0, 0.0, 0.0]
    end
    @parameters begin
        m_nom::Real = 1.3, [unit = "kg", min = 0, description = "Nominal mass of the thrust feedforward"]
        g0::Real = 9.81, [unit = "m/s^2"]
        Kp_xy::Real = 1.0, [unit = "1/s", description = "Horizontal position gain"]
        Kp_z::Real = 1.5, [unit = "1/s", description = "Vertical position gain"]
        Kv_xy::Real = 3.0, [unit = "1/s", description = "Horizontal velocity P gain"]
        Kv_z::Real = 5.0, [unit = "1/s", description = "Vertical velocity P gain"]
        Ki_xy::Real = 1.0, [unit = "1/s^2", description = "Horizontal velocity I gain"]
        Ki_z::Real = 2.0, [unit = "1/s^2", description = "Vertical velocity I gain"]
        Kd_xy::Real = 0.1, [description = "Horizontal velocity D gain (on the measurement)"]
        Kd_z::Real = 0.1, [description = "Vertical velocity D gain (on the measurement)"]
        d_alpha::Real = 0.4, [description = "First-order filter factor of the D term per tick"]
        i_max_xy::Real = 2.0, [unit = "m/s^2", description = "Horizontal integral limit"]
        i_max_z::Real = 3.0, [unit = "m/s^2", description = "Vertical integral limit"]
        v_max_xy::Real = 2.0, [unit = "m/s", description = "Horizontal speed limit"]
        v_up::Real = 1.5, [unit = "m/s", description = "Climb speed limit"]
        v_down::Real = 1.0, [unit = "m/s", description = "Descent speed limit"]
        tilt_max::Real = 0.4363323129985824, [unit = "rad", description = "Tilt limit of the thrust vector (25 deg)"]
        F_max::Real = 34.0, [unit = "N", description = "Collective thrust limit"]
    end
    @variables begin
        iv::Vec{3} = [0.0, 0.0, 0.0], [description = "Velocity integral (acceleration)"]
        vprev::Vec{3} = [0.0, 0.0, 0.0], [description = "Velocity of the previous tick"]
        dfilt::Vec{3} = [0.0, 0.0, 0.0], [description = "Filtered velocity derivative"]
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
        if armed > 0.5
            iv = [
                clamp(iv[1] + Ki_xy * ev[1] * Ts, -i_max_xy, i_max_xy),
                clamp(iv[2] + Ki_xy * ev[2] * Ts, -i_max_xy, i_max_xy),
                clamp(iv[3] + Ki_z * ev[3] * Ts, -i_max_z, i_max_z)
            ]
        else
            iv = [0.0, 0.0, 0.0]
        end
        ac = [
            Kv_xy * ev[1] + iv[1] - Kd_xy * dfilt[1] + a_sp[1],
            Kv_xy * ev[2] + iv[2] - Kd_xy * dfilt[2] + a_sp[2],
            Kv_z * ev[3] + iv[3] - Kd_z * dfilt[3] + a_sp[3]
        ]
        fz = max(m_nom * (ac[3] + g0), 0.3 * m_nom * g0)
        fh = sqrt(m_nom * m_nom * (ac[1] * ac[1] + ac[2] * ac[2]))
        sc = min(1.0, fz * tan(tilt_max) / max(fh, 1.0e-9))
        Fv = [m_nom * ac[1] * sc, m_nom * ac[2] * sc, fz]
        zd = Fv / norm(Fv)
        zb = [
            2 * (q[2] * q[4] + q[1] * q[3]),
            2 * (q[3] * q[4] - q[1] * q[2]),
            q[1] * q[1] - q[2] * q[2] - q[3] * q[3] + q[4] * q[4]
        ]
        xc = [cos(psi_sp), sin(psi_sp), 0.0]
        yd0 = cross(zd, xc)
        yd = yd0 / norm(yd0)
        xd = cross(yd, zd)
        w4 = 0.5 * sqrt(max(1.0 + xd[1] + yd[2] + zd[3], 1.0e-6))
        if armed > 0.5
            F = clamp(dot(Fv, zb), 0.0, F_max)
            qd = [w4, (yd[3] - zd[2]) / (4 * w4), (zd[1] - xd[3]) / (4 * w4), (xd[2] - yd[1]) / (4 * w4)]
        else
            F = 0.0
            qd = [1.0, 0.0, 0.0, 0.0]
        end
        a_cmd = ac
    end
end
