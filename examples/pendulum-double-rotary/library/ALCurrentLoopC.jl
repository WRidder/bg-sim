@block ALCurrentLoopC begin
    # The q-axis current loop of the SOMANET Circulo drive as its continuous-time equivalent, for
    # the long runs. The real loop is digital at 16 kHz (ALCurrentLoop, used by the current-step
    # identification); at a 1.5 kHz loop bandwidth against a mechanical crossover near 9 Hz its
    # sampling is invisible to the mechanics, while a 16 kHz held output would make the run record
    # 32 000 event rows per second. Kept from the digital loop: the same PI (zero on the winding
    # pole), the voltage clamp to the linear SVPWM range +-umax, anti-windup, and the loop's
    # transport delay (computation + PWM update, 1.5 periods) as a first-order lag t_d.
    #
    # The bond graph carries the winding as an equivalent DC circuit with the flow ie = 1.5 i_q;
    # iq = ie / 1.5.
    @inputs begin
        iref::Real, [unit = "A", description = "q current reference (amplitude)"]
        ie::Real, [unit = "A", description = "Bond-graph winding flow 1.5 i_q"]
    end
    @outputs begin
        uq::Real, [unit = "V", description = "q voltage command"]
        iq::Real, [unit = "A", description = "q current"]
    end
    @parameters begin
        kp::Real = 1.036, [unit = "V/A", description = "Proportional gain"]
        ki::Real = 1837.0, [unit = "V/(A*s)", description = "Integral gain"]
        umax::Real = 26.3, [unit = "V", min = 0, description = "Voltage limit (linear SVPWM)"]
        t_d::Real = 9.375e-5, [unit = "s", min = 0, description = "Transport delay as a lag (1.5 periods of 16 kHz)"]
    end
    @variables begin
        integ::Real = 0.0, [unit = "V", description = "Integrator"]
        ud::Real = 0.0, [unit = "V", description = "Applied (lagged) voltage"]
    end
    @equations begin
        iq ~ ie / 1.5
        ddt(integ) ~ ki * (iref - iq) + (ki / kp) * (clamp(kp * (iref - iq) + integ, -umax, umax) - (kp * (iref - iq) + integ))
        ddt(ud) ~ (clamp(kp * (iref - iq) + integ, -umax, umax) - ud) / t_d
        uq ~ ud
    end
end
