@block ServoCurrentLoop begin
    # Plan 9.6b: the innermost sampled loop. One 8 kHz tick does a PI on i_d and i_q
    # (pole-zero cancellation in design/design.py), adds the dq cross-coupling and the
    # back-EMF feedforward, and limits the voltage vector to V_dc/sqrt(3).  The plant is
    # the bond graph; this block only produces the two averaged voltage commands.
    @constants sample_period::Real = 125.0e-6, [unit = "s", min = 1.0e-12, description = "Current-loop sample period (8 kHz)"]
    @parameters begin
        Ld::Real = 0.006, [unit = "H", min = 0.0, description = "d-axis inductance"]
        Lq::Real = 0.006, [unit = "H", min = 0.0, description = "q-axis inductance"]
        psi::Real = 0.08, [unit = "V*s", min = 0.0, description = "Permanent-magnet flux linkage"]
        pp::Int = 4, [min = 1, description = "Pole pairs"]
        Kp_d::Real = 18.85, [unit = "V/A", description = "d-axis proportional gain"]
        Ki_d::Real = 1570.8, [unit = "V/(A*s)", description = "d-axis integral gain"]
        Kp_q::Real = 18.85, [unit = "V/A", description = "q-axis proportional gain"]
        Ki_q::Real = 1570.8, [unit = "V/(A*s)", description = "q-axis integral gain"]
        vmax::Real = 173.205, [unit = "V", min = 0.0, description = "Voltage vector limit, V_dc/sqrt(3)"]
        imax::Real = 15.0, [unit = "A", min = 0.0, description = "Current command limit"]
    end
    @inputs begin
        id::Real
        iq::Real
        w_m::Real
        id_cmd::Real
        iq_cmd::Real
    end
    @outputs begin
        vd::Real = 0.0, [unit = "V"]
        vq::Real = 0.0, [unit = "V"]
        vmag::Real = 0.0, [unit = "V"]
        id_ref::Real = 0.0, [unit = "A"]
        iq_ref::Real = 0.0, [unit = "A"]
    end
    @variables begin
        integ_d::Real = 0.0, [description = "d-axis integral term"]
        integ_q::Real = 0.0, [description = "q-axis integral term"]
    end
    @discrete Ts = sample_period begin
        we = pp * w_m
        id_ref = clamp(id_cmd, -imax, imax)
        iq_ref = clamp(iq_cmd, -imax, imax)
        ed = id_ref - id
        eq = iq_ref - iq
        integ_d += Ki_d * Ts * ed
        integ_q += Ki_q * Ts * eq
        vd = Kp_d * ed + integ_d - we * Lq * iq
        vq = Kp_q * eq + integ_q + we * (Ld * id + psi)
        vmag = sqrt(vd * vd + vq * vq)
        if vmag > vmax
            scale = vmax / vmag
            vd = vd * scale
            vq = vq * scale
            vmag = vmax
            integ_d -= Ki_d * Ts * ed
            integ_q -= Ki_q * Ts * eq
        end
    end
end
