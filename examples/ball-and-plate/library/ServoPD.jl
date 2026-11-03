@block ServoPD begin
    # Position loop of one servo, the inner loop of the cascade (firmware at 500 Hz, like the
    # QUARC servo loop of a lab rig or the PD of a digital hobby servo): a PD on the encoder
    # angle with the derivative on the measurement (no kick on a set-point step), filtered by a
    # first-order low pass,
    #   d_k = a d_{k-1} + (1 - a) (th_k - th_{k-1}) / Ts,  a = tau_f / (tau_f + Ts),
    #   V_k = clamp(Kp (ref_k - th_k) - Kd d_k, -V_max, V_max).
    # The set-point is clamped to the servo travel +-th_max first. design/design.py sets the gains
    # (natural frequency 50 rad/s, damping 0.8 with the plate reflected through the crank).
    @inputs begin
        ref::Real, [unit = "rad", description = "Servo angle set-point (from the outer loop)"]
        theta::Real, [unit = "rad", description = "Measured servo angle (encoder)"]
    end
    @outputs begin
        V::Real = 0.0, [unit = "V", description = "Motor voltage command"]
        rate::Real = 0.0, [unit = "rad/s", description = "Filtered servo speed"]
    end
    @parameters begin
        Kp::Real = 27.87, [unit = "V/rad", tunable = true, description = "Proportional gain"]
        Kd::Real = 0.2817, [unit = "V*s/rad", tunable = true, description = "Derivative gain (on the measurement)"]
        tau_f::Real = 0.002, [unit = "s", min = 0, description = "Derivative filter time constant"]
        V_max::Real = 10.0, [unit = "V", min = 0, description = "Voltage limit (DAQ output range)"]
        th_max::Real = 1.0471975511965976, [unit = "rad", min = 0, description = "Servo travel limit of the set-point"]
    end
    @variables begin
        tp::Real = 0.0, [unit = "rad", description = "Encoder angle of the previous tick"]
        d::Real = 0.0, [unit = "rad/s", description = "Filtered speed"]
        init::Real = 1.0, [description = "First tick"]
    end
    @discrete Ts = 0.002 begin
        if init > 0.5
            tp = theta
            init = 0.0
        end
        a = tau_f / (tau_f + Ts)
        d = a * d + (1.0 - a) * (theta - tp) / Ts
        tp = theta
        r = clamp(ref, -th_max, th_max)
        V = clamp(Kp * (r - theta) - Kd * d, -V_max, V_max)
        rate = d
    end
end
