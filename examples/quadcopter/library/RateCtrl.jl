@block RateCtrl begin
    # 500 Hz body-rate PID (the inner loop of the cascade). Output is a physical torque
    # demand (N m) about the body axes for the mixer.
    #
    #   tau = Kp (w_sp - w) + I - Kd dw_f/dt,    I <- I + Ki (w_sp - w) Ts
    #
    # The derivative acts on the (bias-corrected, low-pass filtered) measurement, not on the error,
    # so set-point steps do not kick, and goes through a first-order filter (`d_alpha` per tick).
    # Anti-windup: the torque is clamped to +-tau_max and the integral is not advanced while the
    # clamp is active and the error pushes further into it (conditional integration); the integral
    # is also limited and held at zero while disarmed. `f_alpha` is a first-order low-pass of the torque demand
    # per axis (1 = off): the yaw axis uses it because the rotor acceleration torque makes the yaw actuator
    # a high-gain lead (design/design.py).
    @inputs begin
        w_sp::Vec{3}
        w::Vec{3}
        armed::Real
    end
    @outputs tau::Vec{3} = [0.0, 0.0, 0.0]
    @parameters begin
        Kp::Vec{3} = [0.4, 0.4, 0.5], [unit = "N*m*s/rad", description = "Proportional gain"]
        Ki::Vec{3} = [3.0, 3.0, 2.0], [unit = "N*m/rad", description = "Integral gain"]
        Kd::Vec{3} = [0.004, 0.004, 0.0], [unit = "N*m*s^2/rad", description = "Derivative gain (on the measurement)"]
        tau_max::Vec{3} = [0.6, 0.6, 0.25], [unit = "N*m", description = "Torque limit per axis"]
        i_max::Vec{3} = [0.2, 0.2, 0.1], [unit = "N*m", description = "Integral limit per axis"]
        d_alpha::Real = 0.25, [description = "First-order filter factor of the D term per tick"]
        f_alpha::Vec{3} = [1.0, 1.0, 1.0], [description = "First-order low-pass factor of the torque demand per tick (1 = none); the yaw axis needs one because of the rotor acceleration torque"]
    end
    @variables begin
        I::Vec{3} = [0.0, 0.0, 0.0], [description = "Integral state"]
        wprev::Vec{3} = [0.0, 0.0, 0.0], [description = "Rate of the previous tick"]
        df::Vec{3} = [0.0, 0.0, 0.0], [description = "Filtered rate derivative"]
        tf::Vec{3} = [0.0, 0.0, 0.0], [description = "Low-passed torque demand"]
    end
    @discrete Ts = 2e-3 begin
        out = [0.0, 0.0, 0.0]
        for k in 1:3
            ek = w_sp[k] - w[k]
            dm = (w[k] - wprev[k]) / Ts
            df[k] = df[k] + d_alpha * (dm - df[k])
            ik = clamp(I[k] + Ki[k] * ek * Ts, -i_max[k], i_max[k])
            u = Kp[k] * ek + ik - Kd[k] * df[k]
            if abs(u) > tau_max[k] && u * ek > 0.0
                ik = I[k]
            end
            if armed > 0.5
                I[k] = ik
                tf[k] = tf[k] + f_alpha[k] * (clamp(Kp[k] * ek + ik - Kd[k] * df[k], -tau_max[k], tau_max[k]) - tf[k])
                out[k] = tf[k]
            else
                I[k] = 0.0
                tf[k] = 0.0
                out[k] = 0.0
            end
        end
        wprev = w
        tau = out
    end
end
