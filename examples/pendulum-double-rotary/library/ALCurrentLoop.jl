@block ALCurrentLoop begin
    # The q-axis current loop of the SOMANET Circulo drive (field-oriented control, d current 0),
    # sampled at 16 kHz (Synapticon docs: torque loop at 16 kHz). A PI on i_q with the zero on the
    # winding pole, the output clamped to the linear SVPWM range +-umax (= 0.95 V_dc/sqrt(3)) and
    # conditional integration as anti-windup. The averaged inverter: u_q is applied as a held
    # voltage (PWM ripple not modelled).
    #
    # The bond graph carries the winding as an equivalent DC circuit with the flow ie = 1.5 i_q (so
    # that u_q ie is the electrical power of the amplitude-invariant dq frame); iq = ie / 1.5.
    @constants sample_period::Real = 6.25e-5, [unit = "s", description = "Current loop period"]
    @inputs begin
        iref::Real, [unit = "A", description = "q current reference (amplitude)"]
        ie::Real, [unit = "A", description = "Bond-graph winding flow 1.5 i_q"]
    end
    @outputs begin
        uq::Real = 0.0, [unit = "V", description = "q voltage command"]
        iq::Real = 0.0, [unit = "A", description = "Sampled q current"]
    end
    @parameters begin
        kp::Real = 1.574, [unit = "V/A", description = "Proportional gain"]
        ki::Real = 2545.0, [unit = "V/(A*s)", description = "Integral gain"]
        umax::Real = 26.3, [unit = "V", min = 0, description = "Voltage limit (linear SVPWM)"]
    end
    @variables integ::Real = 0.0, [unit = "V", description = "Integrator"]
    @discrete Ts = sample_period begin
        i = ie / 1.5
        e = iref - i
        v = kp * e + integ
        uq = clamp(v, -umax, umax)
        if abs(v) < umax || (v > 0.0) != (e > 0.0)
            integ = clamp(integ + ki * Ts * e, -umax, umax)
        end
        iq = i
    end
end
