@block PlatePID begin
    # Outer loop of the cascaded PID (one axis), run at the camera frame rate: the ball position
    # from the camera (already one frame late) against the set-point r, the servo angle set-point
    # out. The derivative acts on the measurement through a first-order filter (no kick on a
    # set-point step), the set-point is weighted by b in the proportional term, and the integral
    # only runs while the error is inside +-e_int (conditional integration, the anti-windup that
    # keeps a large step from charging the integrator):
    #   d_k  = a d_{k-1} + (1 - a) (y_k - y_{k-1}) / Ts,     a = tau_d / (tau_d + Ts)
    #   i_k  = i_{k-1} + Ts e_k   if |e_k| < e_int,          e_k = r_k - y_k
    #   th_r = clamp(Kp (b r_k - y_k) + Ki i_k - Kd d_k, -th_max, th_max)
    # design/design.py tunes the gains on the linear axis model with the camera delay (grid
    # search: overshoot <= 8 %, stable with 2 frames of latency, then the shortest settling).
    @inputs begin
        r::Real, [unit = "m", description = "Ball position set-point"]
        y::Real, [unit = "m", description = "Measured ball position (camera)"]
    end
    @outputs begin
        th_ref::Real = 0.0, [unit = "rad", description = "Servo angle set-point"]
        err::Real = 0.0, [unit = "m", description = "Control error r - y"]
    end
    @parameters begin
        Kp::Real = 3.6, [unit = "rad/m", tunable = true, description = "Proportional gain"]
        Ki::Real = 0.72, [unit = "rad/(m*s)", tunable = true, description = "Integral gain"]
        Kd::Real = 2.52, [unit = "rad*s/m", tunable = true, description = "Derivative gain"]
        tau_d::Real = 0.05, [unit = "s", min = 0, description = "Derivative filter time constant"]
        b::Real = 1.0, [unit = "1", description = "Set-point weight of the proportional term"]
        e_int::Real = 0.01, [unit = "m", min = 0, description = "Error band of the integral"]
        th_max::Real = 1.0471975511965976, [unit = "rad", min = 0, description = "Output limit (servo travel)"]
    end
    @variables begin
        i::Real = 0.0, [unit = "m*s", description = "Integral of the error"]
        d::Real = 0.0, [unit = "m/s", description = "Filtered derivative of the measurement"]
        yp::Real = 0.0, [unit = "m", description = "Measurement of the previous tick"]
        init::Real = 1.0, [description = "First tick"]
    end
    @discrete Ts = 0.033333333 begin
        if init > 0.5
            yp = y
            init = 0.0
        end
        e = r - y
        if abs(e) < e_int
            i = i + Ts * e
        end
        a = tau_d / (tau_d + Ts)
        d = a * d + (1.0 - a) * (y - yp) / Ts
        yp = y
        th_ref = clamp(Kp * (b * r - y) + Ki * i - Kd * d, -th_max, th_max)
        err = e
    end
end
