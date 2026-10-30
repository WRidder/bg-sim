@block NavFilter begin
    # 250 Hz navigation filter: attitude, velocity, position and gyro bias from the filtered IMU
    # and the 50 Hz position/velocity/heading fix. A fixed-gain (steady-state) observer in the
    # complementary-filter form; the gains come from design/design.py.
    #
    # A multirotor accelerometer measures the thrust, not gravity (the specific force always points
    # along the body z axis, up to drag), so the usual "gravity direction" tilt correction is wrong
    # in flight. The tilt is observed through the velocity instead: a tilt error rotates the world
    # specific force and shows up as a velocity innovation.
    #
    #   propagate    q <- q (x) exp(w_hat Ts / 2),  w_hat = gyro - bg + w_c        (body rates)
    #                v <- v + Ts (R f + g + L2 ep + L3 ev),   p <- p + Ts (v + L1 ep)
    #   innovations  ep = p_gps - p,  ev = v_gps - v,  epsi = wrap(psi_mag - psi_hat)
    #   attitude     w_c(world) = kth (R f x ev) / |R f|^2  with the yaw part kpsi epsi
    #                (the velocity error rate is -(R f) x dtheta, so this closes the loop with
    #                characteristic polynomial s^2 + L3 s + kth)
    #   gyro bias    bg <- bg - kb w_c(body) Ts
    #
    # The estimate starts aligned (identity attitude, `p0` position): the airframe is at rest on
    # the ground at power-up.
    @inputs begin
        gyro::Vec{3}
        acc::Vec{3}
        pm::Vec{3}
        vm::Vec{3}
        psim::Real
        n::Real
    end
    @outputs begin
        q::Vec{4} = [1.0, 0.0, 0.0, 0.0]
        p::Vec{3} = [0.0, 0.0, 0.0]
        v::Vec{3} = [0.0, 0.0, 0.0]
        w::Vec{3} = [0.0, 0.0, 0.0]
        bg::Vec{3} = [0.0, 0.0, 0.0]
        yaw::Real = 0.0
    end
    @parameters begin
        g0::Real = 9.81, [unit = "m/s^2", description = "Gravity used to remove it from the specific force"]
        L1::Real = 6.0, [unit = "1/s", description = "Position correction gain"]
        L2::Real = 9.0, [unit = "1/s^2", description = "Velocity correction gain from the position innovation"]
        L3::Real = 6.0, [unit = "1/s", description = "Velocity correction gain from the velocity innovation"]
        kth::Real = 8.0, [unit = "1/s^2", description = "Tilt correction gain"]
        kb::Real = 1.0, [unit = "1/s", description = "Gyro bias gain"]
        kpsi::Real = 2.0, [unit = "1/s", description = "Heading correction gain"]
    end
    @variables begin
        qs::Vec{4} = [1.0, 0.0, 0.0, 0.0], [description = "Attitude state"]
        ps::Vec{3} = [0.0, 0.0, 0.0], [description = "Position state"]
        vs::Vec{3} = [0.0, 0.0, 0.0], [description = "Velocity state"]
        bs::Vec{3} = [0.0, 0.0, 0.0], [description = "Gyro bias state"]
    end
    @discrete Ts = 4e-3 begin
        q0 = qs[1]
        q1 = qs[2]
        q2 = qs[3]
        q3 = qs[4]
        r11 = q0 * q0 + q1 * q1 - q2 * q2 - q3 * q3
        r12 = 2 * (q1 * q2 - q0 * q3)
        r13 = 2 * (q1 * q3 + q0 * q2)
        r21 = 2 * (q1 * q2 + q0 * q3)
        r22 = q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3
        r23 = 2 * (q2 * q3 - q0 * q1)
        r31 = 2 * (q1 * q3 - q0 * q2)
        r32 = 2 * (q2 * q3 + q0 * q1)
        r33 = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3
        Fw = [r11 * acc[1] + r12 * acc[2] + r13 * acc[3], r21 * acc[1] + r22 * acc[2] + r23 * acc[3], r31 * acc[1] + r32 * acc[2] + r33 * acc[3]]
        aw = Fw + [0.0, 0.0, -g0]
        gate = ifelse(n > 0.5, 1.0, 0.0)
        ep = gate * (pm - ps)
        ev = gate * (vm - vs)
        yawh = atan(2 * (q0 * q3 + q1 * q2), 1 - 2 * (q2 * q2 + q3 * q3))
        e0 = gate * (psim - yawh)
        epsi = e0 - 6.283185307179586 * round(e0 / 6.283185307179586)
        Fn2 = max(dot(Fw, Fw), 4.0)
        cx = cross(Fw, ev)
        wcw = [kth * cx[1] / Fn2, kth * cx[2] / Fn2, kpsi * epsi]
        wcb = [r11 * wcw[1] + r21 * wcw[2] + r31 * wcw[3], r12 * wcw[1] + r22 * wcw[2] + r32 * wcw[3], r13 * wcw[1] + r23 * wcw[2] + r33 * wcw[3]]
        om = gyro - bs + wcb
        bs = bs - kb * wcb * Ts
        ps = ps + Ts * (vs + L1 * ep) + 0.5 * Ts * Ts * aw
        vs = vs + Ts * (aw + L2 * ep + L3 * ev)
        dq = 0.5 * Ts * om
        n0 = q0 - dq[1] * q1 - dq[2] * q2 - dq[3] * q3
        n1 = q1 + dq[1] * q0 + dq[3] * q2 - dq[2] * q3
        n2 = q2 + dq[2] * q0 + dq[1] * q3 - dq[3] * q1
        n3 = q3 + dq[3] * q0 + dq[2] * q1 - dq[1] * q2
        nn = 1.0 / sqrt(n0 * n0 + n1 * n1 + n2 * n2 + n3 * n3)
        qs = [n0 * nn, n1 * nn, n2 * nn, n3 * nn]
        q = qs
        p = ps
        v = vs
        w = gyro - bs
        bg = bs
        yaw = yawh
    end
end
