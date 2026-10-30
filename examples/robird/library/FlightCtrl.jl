@block FlightCtrl begin
    # Cycle-averaged flight controller of the flapping bird, 100 Hz (inner attitude/speed loops). It sees the
    # attitude quaternion, the body rates and the ground velocity (state feedback from the `Truth` tap; the
    # flapping oscillation of those signals is attenuated by the loop bandwidth, a few rad/s, versus the flapping
    # at 12 to 28 rad/s - design/design.py measures the ripple that gets through).
    #
    # Conventions: nose-up pitch theta, roll phi about body x (left wing UP positive), q_up = -wb[2].
    #
    #   speed      f = f0 + Kpu (U_cmd - U) + Iu + Kfn (n - 1),            n = 1/cos(phi) the load factor
    #   altitude   vz_cmd = clamp(Kz (z_ref - z) + vz_ff),   theta_cmd = th0 + Kth_n (n - 1) + Kpv (vz_cmd - vz) + Ivz
    #   pitch      de = de0 - Kth (theta_cmd - theta) + Kq q_up                (elevator: tail leading edge up = nose down)
    #   bank       phi_cmd = -atan(U psid / g)                                 (coordinated turn, left turn = left wing down)
    #              da = Kphi (phi_cmd - phi) - Kp p + Iphi ,  eta = Keta (phi_cmd - phi)
    #   yaw        dr = -Kr (psid cos(phi) - r)                                (rudder: damping + turn coordination)
    #
    # The tail halves get de +- da (elevons), the fin dr, the flapping drive the frequency f and the wing
    # amplitude asymmetry (1 + eta, 1 - eta). All commands are limited; the integrators have anti-windup by clamping.
    @inputs begin
        q::Vec{4}
        wb::Vec{3}
        vw::Vec{3}
        zp::Real
        psid::Real
        z_ref::Real
        vz_ff::Real
    end
    @outputs begin
        f_cmd::Real = 4.0, [unit = "Hz"]
        sp_L::Real = 0.0, [unit = "rad"]
        sp_R::Real = 0.0, [unit = "rad"]
        sp_V::Real = 0.0, [unit = "rad"]
        aL::Real = 1.0
        aR::Real = 1.0
        phi::Real = 0.0, [unit = "rad"]
        theta::Real = 0.0, [unit = "rad"]
        psi::Real = 0.0, [unit = "rad"]
        phi_cmd::Real = 0.0, [unit = "rad"]
        theta_cmd::Real = 0.0, [unit = "rad"]
        speed::Real = 0.0, [unit = "m/s"]
        de::Real = 0.0, [unit = "rad"]
        da::Real = 0.0, [unit = "rad"]
        dr::Real = 0.0, [unit = "rad"]
    end
    @parameters begin
        U_cmd::Real = 12.0, [unit = "m/s"]
        g0::Real = 9.81
        f0::Real = 3.4, [unit = "Hz", description = "Trim flapping frequency"]
        de0::Real = 0.0, [unit = "rad", description = "Trim elevator"]
        th0::Real = 0.08, [unit = "rad", description = "Trim pitch attitude"]
        Kpu::Real = 0.3, [unit = "Hz*s/m"]
        Kiu::Real = 0.15, [unit = "Hz/m"]
        Kfn::Real = 3.0, [unit = "Hz"]
        Kz::Real = 0.25, [unit = "1/s"]
        vz_max::Real = 2.0, [unit = "m/s"]
        Kpv::Real = 0.06, [unit = "rad*s/m"]
        Kiv::Real = 0.04, [unit = "rad/m"]
        Kth_n::Real = 0.1, [unit = "rad"]
        Kth::Real = 0.5, [description = "Elevator per pitch error"]
        Kq::Real = 0.05, [unit = "s", description = "Elevator per pitch rate"]
        Kphi::Real = 0.8, [description = "Differential tail per roll error"]
        Kp::Real = 0.05, [unit = "s", description = "Differential tail per roll rate"]
        Kiphi::Real = 0.1, [unit = "1/s"]
        Keta::Real = 0.0, [description = "Wing amplitude asymmetry per roll error"]
        Kr::Real = 0.15, [unit = "s", description = "Rudder per yaw-rate error"]
        phi_max::Real = 0.6, [unit = "rad"]
        f_min::Real = 2.0, [unit = "Hz"]
        f_max::Real = 4.5, [unit = "Hz"]
        d_max::Real = 0.45, [unit = "rad"]
        rn::Real = 0.95, [description = "Pole radius of the cycle-averaging notch filters"]
    end
    @variables begin
        Iu::Real = 0.0, [unit = "Hz"]
        Ivz::Real = 0.0, [unit = "rad"]
        Iphi::Real = 0.0, [unit = "rad"]
        nax1::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nax2::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nay1::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nay2::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nbx1::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nbx2::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nby1::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        nby2::Vec{8} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        first::Real = 1.0
    end
    @discrete Ts = 10e-3 begin
        s2 = q[1] * q[1] + q[2] * q[2] + q[3] * q[3] + q[4] * q[4]
        r21 = 2.0 * (q[2] * q[3] + q[1] * q[4]) / s2
        r11 = (q[1] * q[1] + q[2] * q[2] - q[3] * q[3] - q[4] * q[4]) / s2
        r31 = 2.0 * (q[2] * q[4] - q[1] * q[3]) / s2
        r32 = 2.0 * (q[3] * q[4] + q[1] * q[2]) / s2
        r33 = (q[1] * q[1] - q[2] * q[2] - q[3] * q[3] + q[4] * q[4]) / s2
        ph = atan(r32, r33)
        th = asin(clamp(r31, -1.0, 1.0))
        U = sqrt(vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3])
        # cycle averaging: two notch filters, at the flapping frequency and its second harmonic (centre frequency
        # = the commanded frequency of the last tick), unit gain at DC, applied to the feedback signals
        raw = [th, -wb[2], ph, wb[1], wb[3], vw[3], sqrt(vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3]), 0.0]
        ca = cos(2.0 * 3.141592653589793 * f_cmd * Ts)
        cb = cos(4.0 * 3.141592653589793 * f_cmd * Ts)
        ba = (1.0 - 2.0 * rn * ca + rn * rn) / (2.0 - 2.0 * ca)
        bb = (1.0 - 2.0 * rn * cb + rn * rn) / (2.0 - 2.0 * cb)
        fil = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for k in 1:8
            xk = ifelse(first > 0.5, raw[k], raw[k])
            ya = ba * (xk - 2.0 * ca * nax1[k] + nax2[k]) + 2.0 * rn * ca * nay1[k] - rn * rn * nay2[k]
            ya = ifelse(first > 0.5, xk, ya)
            nax2[k] = nax1[k]
            nax1[k] = xk
            nay2[k] = ifelse(first > 0.5, xk, nay1[k])
            nay1[k] = ya
            yb = bb * (ya - 2.0 * cb * nbx1[k] + nbx2[k]) + 2.0 * rn * cb * nby1[k] - rn * rn * nby2[k]
            yb = ifelse(first > 0.5, ya, yb)
            nbx2[k] = nbx1[k]
            nbx1[k] = ya
            nby2[k] = ifelse(first > 0.5, ya, nby1[k])
            nby1[k] = yb
            fil[k] = yb
        end
        first = 0.0
        thf = fil[1]
        qupf = fil[2]
        phf = fil[3]
        pf = fil[4]
        rf = fil[5]
        vzf = fil[6]
        Uf = fil[7]
        cph = max(cos(phf), 0.5)
        nl = 1.0 / cph
        # speed loop (flapping frequency)
        eU = U_cmd - Uf
        Iu = clamp(Iu + Kiu * eU * Ts, -1.5, 1.5)
        fc = clamp(f0 + Kpu * eU + Iu + Kfn * (nl - 1.0), f_min, f_max)
        # altitude -> climb rate -> pitch attitude -> elevator
        vzc = clamp(Kz * (z_ref - zp) + vz_ff, -vz_max, vz_max)
        evz = vzc - vzf
        Ivz = clamp(Ivz + Kiv * evz * Ts, -0.25, 0.25)
        thc = clamp(th0 + Kth_n * (nl - 1.0) + Kpv * evz + Ivz, -0.3, 0.45)
        dev = clamp(de0 - Kth * (thc - thf) + Kq * qupf, -d_max, d_max)
        # bank
        phc = clamp(-atan(Uf * psid / g0), -phi_max, phi_max)
        ephi = phc - phf
        Iphi = clamp(Iphi + Kiphi * ephi * Ts, -0.2, 0.2)
        dav = clamp(Kphi * ephi - Kp * pf + Iphi, -d_max, d_max)
        drv = clamp(-Kr * (psid * cph - rf), -d_max, d_max)
        et = clamp(Keta * ephi, -0.3, 0.3)
        f_cmd = fc
        sp_L = dev + dav
        sp_R = dev - dav
        sp_V = drv
        aL = 1.0 + et
        aR = 1.0 - et
        phi = ph
        theta = th
        psi = atan(r21, r11)
        phi_cmd = phc
        theta_cmd = thc
        speed = U
        de = dev
        da = dav
        dr = drv
    end
end
