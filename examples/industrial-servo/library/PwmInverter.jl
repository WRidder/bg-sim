@block PwmInverter begin
    # Plan 9.6b `switching` variant: a two-level voltage-source inverter with a sampled
    # carrier, dead time and device drops.  The dq voltage command is transformed to abc with
    # the measured electrical angle, min-max (SVPWM) zero-sequence injection is added, and
    # each leg is compared with a triangle at `sample_period` (25 samples per 4 kHz carrier).
    # The applied leg voltage loses (Td/Tpwm)*Vdc + Vdrop on the sign of the phase current,
    # and the three phase voltages are transformed back to dq.  Only this switching logic and
    # the abc<->dq transforms are code; the motor stays the dq bond graph.  The carrier phase
    # is a function of `t` (not a held state), so the output only changes at a leg edge.
    @constants sample_period::Real = 10.0e-6, [unit = "s", min = 1.0e-12, description = "PWM comparator sample period (100 kHz)"]
    @parameters begin
        Vdc::Real = 300.0, [unit = "V", min = 0.0, description = "DC bus voltage"]
        Tpwm::Real = 250.0e-6, [unit = "s", min = 1.0e-12, description = "PWM carrier period (4 kHz)"]
        Td::Real = 2.0e-6, [unit = "s", min = 0.0, description = "Dead time per leg"]
        Vdrop::Real = 1.2, [unit = "V", min = 0.0, description = "Conduction drop per leg (two devices)"]
    end
    @inputs begin
        vd::Real, [unit = "V"]
        vq::Real, [unit = "V"]
        theta_e::Real, [unit = "rad"]
        id::Real, [unit = "A"]
        iq::Real, [unit = "A"]
    end
    @outputs begin
        vd_app::Real = 0.0, [unit = "V"]
        vq_app::Real = 0.0, [unit = "V"]
        va::Real = 0.0, [unit = "V"]
        vb::Real = 0.0, [unit = "V"]
        vc::Real = 0.0, [unit = "V"]
    end
    @discrete Ts = sample_period begin
        ca = cos(theta_e)
        sa = sin(theta_e)
        cb = cos(theta_e - 2.0943951023931953)
        sb = sin(theta_e - 2.0943951023931953)
        cc = cos(theta_e + 2.0943951023931953)
        sc = sin(theta_e + 2.0943951023931953)
        # inverse Park (amplitude invariant)
        va_ref = vd * ca - vq * sa
        vb_ref = vd * cb - vq * sb
        vc_ref = vd * cc - vq * sc
        # min-max zero-sequence injection: the linear range becomes Vdc/sqrt(3)
        v_hi = max(va_ref, max(vb_ref, vc_ref))
        v_lo = min(va_ref, min(vb_ref, vc_ref))
        v0 = -(v_hi + v_lo) / 2.0
        da = 0.5 + (va_ref + v0) / Vdc
        db = 0.5 + (vb_ref + v0) / Vdc
        dc = 0.5 + (vc_ref + v0) / Vdc
        # phase currents for the sign of the dead-time and device-drop errors
        ia = id * ca - iq * sa
        ib = id * cb - iq * sb
        ic = id * cc - iq * sc
        # sampled center-aligned carrier in [-1, 1], from the tick time
        phase = mod(t / Tpwm, 1.0)
        carrier = 1.0 - 2.0 * abs(2.0 * phase - 1.0)
        loss = Td / Tpwm * Vdc
        va_l = ifelse(2.0 * da - 1.0 > carrier, 0.5 * Vdc, -0.5 * Vdc)
        vb_l = ifelse(2.0 * db - 1.0 > carrier, 0.5 * Vdc, -0.5 * Vdc)
        vc_l = ifelse(2.0 * dc - 1.0 > carrier, 0.5 * Vdc, -0.5 * Vdc)
        va_l = va_l - (loss + Vdrop) * sign(ia)
        vb_l = vb_l - (loss + Vdrop) * sign(ib)
        vc_l = vc_l - (loss + Vdrop) * sign(ic)
        # phase-to-star voltages (remove the zero sequence) and the forward Park transform
        v0_l = (va_l + vb_l + vc_l) / 3.0
        va = va_l - v0_l
        vb = vb_l - v0_l
        vc = vc_l - v0_l
        vd_app = 2.0 / 3.0 * (va * ca + vb * cb + vc * cc)
        vq_app = -2.0 / 3.0 * (va * sa + vb * sb + vc * sc)
    end
end
