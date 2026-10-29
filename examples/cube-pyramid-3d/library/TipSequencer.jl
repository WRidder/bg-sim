@block TipSequencer begin
    # 1 ms scripted face -> edge -> corner controller for the pyramid cube (X-MB5), sampled
    # firmware (D28). It outputs the body torque `Tx, Ty, Tz` (body frame) that the
    # allocator turns into wheel currents.
    #
    # Measurement. `g` is the world pose of the cube (quaternion first) and `V` its twist
    # [w; v] in the body frame. The firmware uses only the attitude through
    #
    #   u = R^T e_z       the world vertical seen from the body (third row of R(q)),
    #
    # and the angular velocity `w`. Cube on a face: u = (0, 0, 1); on the edge y = z = -a/2:
    # u = (0, sin f, cos f) with f = 45 deg at the balance point; balanced on the vertex
    # (-a/2, -a/2, -a/2): u = (1, 1, 1)/sqrt 3.
    #
    # Script (times in s, `kff` ramps are linear):
    #   phase 0, t < t1                       rest on the face, no torque
    #   phase 1, t1 .. t1+Tf+Tr1             edge pivot r_e = (0, h, h), h = a/2: the wheels first
    #                                        take over the gravity torque about the edge (kff
    #                                        ramp over Tf), then the reference u_ref moves from the
    #                                        face to the edge balance in Tr1 (minimum-jerk blend)
    #   phase 2, until t2                     edge balance: u_ref fixed, feedback only
    #   phase 3, t2 .. t2+Tf+Tr2             corner pivot r_c = (h, h, h): the same, to the vertex
    #                                        balance u = (1, 1, 1)/sqrt 3
    #   phase 4, after                        vertex balance
    #
    # Torque law (all vectors in the body frame):
    #   T = m g0 (r x u)  +  sat( Kp (u_ref x u) + Kd (w_ref - w_perp) - Ky (w . u) u )
    # The first term is the gravity compensation about the pivot (the torque of the weight about
    # the pivot, with the lever `r` from the pivot to the centre of mass; zero at the balance
    # point). It makes the cube a free rotor about the contact feature. The second is the
    # attitude feedback on u (u_ref x u rotates u towards u_ref), w_perp is the angular
    # velocity without its vertical part, w_ref = (du_ref/dt) x u_ref, and the yaw rate about
    # the vertical is damped with Ky. The feedback is limited to `fb_max` (N m) so that it
    # never takes the torque budget of the gravity compensation. A gyroscopic decoupling term
    # w x h (h = wheel momentum from the measured wheel speeds) is added to the command.
    @parameters begin
        m::Real = 1.4, [unit = "kg", min = 0, description = "Total mass of the cube and the wheels"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        a::Real = 0.2, [unit = "m", min = 1.0e-6, description = "Cube edge length"]
        t1::Real = 1.0, [unit = "s", description = "Start of the face-to-edge move"]
        t2::Real = 4.0, [unit = "s", description = "Start of the edge-to-corner move"]
        Tf::Real = 0.15, [unit = "s", min = 1.0e-6, description = "Ramp-in of the gravity compensation"]
        Tr1::Real = 0.5, [unit = "s", min = 1.0e-6, description = "Duration of the face-to-edge reference move"]
        Tr2::Real = 0.7, [unit = "s", min = 1.0e-6, description = "Duration of the edge-to-corner reference move"]
        Kp::Real = 5.0, [unit = "N*m", min = 0, description = "Attitude gain on u_ref x u"]
        Kd::Real = 1.2, [unit = "N*m*s", min = 0, description = "Rate gain"]
        Ky::Real = 0.05, [unit = "N*m*s", min = 0, description = "Yaw-rate gain"]
        beta::Real = 0.9553166181245093, [unit = "rad", description = "Wheel axis tilt from the body z axis"]
        Jw::Real = 2.0e-3, [unit = "kg*m^2", min = 0, description = "Axial inertia of one wheel (for the wheel momentum estimate)"]
        fb_max::Real = 0.8, [unit = "N*m", min = 0, description = "Limit of the feedback torque"]
    end
    @inputs begin
        g::Vec{7}
        V::Vec{6}
        w1::Real, [unit = "rad/s", description = "Wheel 1 speed relative to the body"]
        w2::Real, [unit = "rad/s", description = "Wheel 2 speed"]
        w3::Real, [unit = "rad/s", description = "Wheel 3 speed"]
        w4::Real, [unit = "rad/s", description = "Wheel 4 speed"]
    end
    @outputs begin
        Tx::Real = 0.0
        Ty::Real = 0.0
        Tz::Real = 0.0
        ph::Real = 0.0
        ex::Real = 0.0
        ey::Real = 0.0
        ez::Real = 0.0
    end
    @variables begin
        pux::Real = 0.0
        puy::Real = 0.0
        puz::Real = 1.0
    end
    @discrete Ts = 1e-3 begin
        s2 = g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        ux = 2 * (g[2] * g[4] - g[1] * g[3]) / s2
        uy = 2 * (g[3] * g[4] + g[1] * g[2]) / s2
        uz = (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s2
        h = 0.5 * a
        c45 = 0.7071067811865476
        c3 = 0.5773502691896258
        # Reference u_ref and pivot lever r by phase; kb = blend of the lever from the edge to
        # the corner pivot (0 on the edge, 1 on the vertex).
        rx = 0.0
        rk = 0.0
        qx0 = 0.0
        qy0 = 0.0
        qz0 = 1.0
        qx1 = 0.0
        qy1 = 0.0
        qz1 = 1.0
        s = 0.0
        ph = 0.0
        if t >= t1
            ph = 1.0
            rk = clamp((t - t1) / Tf, 0.0, 1.0)
            qx1 = 0.0
            qy1 = c45
            qz1 = c45
            if t >= t1 + Tf
                x = clamp((t - t1 - Tf) / Tr1, 0.0, 1.0)
                s = x * x * x * (10.0 - 15.0 * x + 6.0 * x * x)
            end
            if t >= t1 + Tf + Tr1
                ph = 2.0
            end
        end
        if t >= t2
            ph = 3.0
            qx0 = 0.0
            qy0 = c45
            qz0 = c45
            qx1 = c3
            qy1 = c3
            qz1 = c3
            rk = 1.0
            rx = clamp((t - t2) / Tf, 0.0, 1.0)
            s = 0.0
            if t >= t2 + Tf
                x = clamp((t - t2 - Tf) / Tr2, 0.0, 1.0)
                s = x * x * x * (10.0 - 15.0 * x + 6.0 * x * x)
            end
            if t >= t2 + Tf + Tr2
                ph = 4.0
            end
        end
        # Blend of the two end vectors, normalised.
        bx = (1.0 - s) * qx0 + s * qx1
        by = (1.0 - s) * qy0 + s * qy1
        bz = (1.0 - s) * qz0 + s * qz1
        bn = sqrt(bx * bx + by * by + bz * bz)
        rux = bx / bn
        ruy = by / bn
        ruz = bz / bn
        # Reference rate w_ref = (du_ref/dt) x u_ref.
        dx = (rux - pux) / Ts
        dy = (ruy - puy) / Ts
        dz = (ruz - puz) / Ts
        wrx = dy * ruz - dz * ruy
        wry = dz * rux - dx * ruz
        wrz = dx * ruy - dy * rux
        pux = rux
        puy = ruy
        puz = ruz
        # Gravity compensation about the pivot: lever r = CoM - pivot, T_ff = m g0 (r x u).
        # Edge pivot r_e = (0, h, h); corner pivot r_c = (h, h, h); `rk` ramps the whole
        # compensation in, `rx` ramps the x component of the lever from the edge to the corner.
        lx = rx * h
        ly = h
        lz = h
        fx = rk * m * g0 * (ly * uz - lz * uy)
        fy = rk * m * g0 * (lz * ux - lx * uz)
        fz = rk * m * g0 * (lx * uy - ly * ux)
        # Attitude feedback.
        ecx = ruy * uz - ruz * uy
        ecy = ruz * ux - rux * uz
        ecz = rux * uy - ruy * ux
        wx = V[1]
        wy = V[2]
        wz = V[3]
        wu = wx * ux + wy * uy + wz * uz
        px = Kp * ecx + Kd * (wrx - (wx - wu * ux)) - Ky * wu * ux
        py = Kp * ecy + Kd * (wry - (wy - wu * uy)) - Ky * wu * uy
        pz = Kp * ecz + Kd * (wrz - (wz - wu * uz)) - Ky * wu * uz
        pn = sqrt(px * px + py * py + pz * pz + 1.0e-18)
        ps = 1.0
        if pn > fb_max
            ps = fb_max / pn
        end
        # Gyroscopic decoupling: wheel momentum h = Jw sum w_k a_k, the body feels -w x h, so the
        # command carries +w x h (the wheel torque is -dh/dt).
        hx = Jw * sin(beta) * (w1 - w3)
        hy = Jw * sin(beta) * (w2 - w4)
        hz = Jw * cos(beta) * (w1 + w2 + w3 + w4)
        Tx = fx + ps * px + (wy * hz - wz * hy)
        Ty = fy + ps * py + (wz * hx - wx * hz)
        Tz = fz + ps * pz + (wx * hy - wy * hx)
        ex = ecx
        ey = ecy
        ez = ecz
    end
end
