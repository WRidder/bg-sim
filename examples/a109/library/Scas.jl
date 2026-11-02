@block Scas begin
    # Stability and control augmentation (ours; the report has no control system), switchable.
    #
    # scas = 1: attitude command / attitude hold in pitch and roll, yaw-rate command / heading
    # hold in yaw, with turn coordination fading in between v_tc1 and v_tc2 of forward airspeed:
    #
    #   theta_cmd = theta_ff(u) - k_th_stick lon        phi_cmd = phi_ff(u) + k_ph_stick lat
    #   r_cmd     = k_r_stick ped + sigma(u) g tan(phi)/max(u, 5)
    #   B1   = B1_ff(u) + Kth (theta - theta_cmd) + Kq q + xth,   xth' = Kith (theta - theta_cmd)
    #   A1   = A1_ff(u) + Kph (phi_cmd - phi) - Kp p + xph,       xph' = Kiph (phi_cmd - phi)
    #   thtr = tr_ff(u) + Kr (r - r_cmd) + xr,                    xr'  = Kir (r - r_cmd)
    #
    # with the *_ff trim feedforward from Lookup1D tables over the forward airspeed (the trim
    # sweep of design/heli_sim.py). scas = 0: the direct angles of the rigging (B1d, A1d, trd) pass
    # and the integrators stop. Angles in deg, rates in deg/s (FRD), speeds in m/s.
    @inputs begin
        lon::Real
        lat::Real
        ped::Real
        u::Real
        theta::Real
        phi::Real
        p::Real
        q::Real
        r::Real
        th_ff::Real
        ph_ff::Real
        B1_ff::Real
        A1_ff::Real
        tr_ff::Real
        B1d::Real
        A1d::Real
        trd::Real
    end
    @outputs begin
        B1::Real
        A1::Real
        thtr::Real
        th_cmd::Real
        ph_cmd::Real
        r_cmd::Real
    end
    @parameters begin
        scas::Real = 1.0, [description = "1: SCAS on (attitude hold); 0: direct"]
        k_th_stick::Real = 15.0, [description = "Pitch attitude per full stick (deg)"]
        k_ph_stick::Real = 30.0, [description = "Bank per full stick (deg)"]
        k_r_stick::Real = 30.0, [description = "Yaw rate per full pedal (deg/s)"]
        v_tc1::Real = 10.0, [description = "Turn coordination starts (m/s)"]
        v_tc2::Real = 20.0, [description = "Turn coordination complete (m/s)"]
        g0::Real = 9.80665
        Kth::Real = 0.6
        Kq::Real = 0.25
        Kith::Real = 0.3
        Kph::Real = 0.35
        Kp::Real = 0.12
        Kiph::Real = 0.15
        Kr::Real = 0.8
        Kir::Real = 0.6
    end
    @variables begin
        xth::Real = 0.0, [state = :prefer]
        xph::Real = 0.0, [state = :prefer]
        xr::Real = 0.0, [state = :prefer]
        sig::Real = 0.0
        eth::Real = 0.0
        eph::Real = 0.0
        er::Real = 0.0
    end
    @equations begin
        th_cmd ~ th_ff - k_th_stick * lon
        ph_cmd ~ ph_ff + k_ph_stick * lat
        sig ~ clamp((u - v_tc1) / (v_tc2 - v_tc1), 0.0, 1.0)
        r_cmd ~ k_r_stick * ped + sig * g0 * tan(phi * 0.017453292519943295) / max(u, 5.0) * 57.29577951308232
        eth ~ theta - th_cmd
        eph ~ ph_cmd - phi
        er ~ r - r_cmd
        ddt(xth) ~ scas * Kith * eth
        ddt(xph) ~ scas * Kiph * eph
        ddt(xr) ~ scas * Kir * er
        B1 ~ scas * (B1_ff + Kth * eth + Kq * q + xth) + (1.0 - scas) * B1d
        A1 ~ scas * (A1_ff + Kph * eph - Kp * p + xph) + (1.0 - scas) * A1d
        thtr ~ scas * (tr_ff + Kr * er + xr) + (1.0 - scas) * trd
    end
end
