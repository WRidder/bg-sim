@block ServoSpeedLoop begin
    # Plan 9.6b: the middle loop at 1 kHz. PI on the speed error (design.py puts the zero at
    # one fifth of the crossover), with the output current clamped to +-i_max and a simple
    # conditional-integration anti-windup.  The reference comes from the 200 Hz position loop
    # (or directly from the speed step in speed mode).
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Speed-loop sample period (1 kHz)"]
    @parameters begin
        Kp::Real = 0.4608, [unit = "A*s/rad", description = "Speed-loop proportional gain"]
        Ki::Real = 46.3, [unit = "A*s^2/rad", description = "Speed-loop integral gain"]
        i_max::Real = 15.0, [unit = "A", min = 0.0, description = "q-axis current limit"]
    end
    @inputs begin
        w_ref::Real
        w_meas::Real
    end
    @outputs begin
        iq_cmd::Real = 0.0, [unit = "A"]
        id_cmd::Real = 0.0, [unit = "A"]
        w_err::Real = 0.0, [unit = "rad/s"]
    end
    @variables begin
        integ::Real = 0.0, [description = "Integral of the speed error"]
    end
    @discrete Ts = sample_period begin
        w_err = w_ref - w_meas
        integ += Ki * Ts * w_err
        v = Kp * w_err + integ
        iq_cmd = clamp(v, -i_max, i_max)
        id_cmd = 0.0
        if abs(v) > i_max
            integ -= Ki * Ts * w_err
        end
    end
end
