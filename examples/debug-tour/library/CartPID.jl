@block CartPID begin
    # The sampled position controller of the debug tour (Ts = 10 ms). It has a bug on
    # purpose: with aw = 0 the integrator keeps integrating while the drive force is
    # saturated (integrator windup), so the cart overshoots and trips the limit switch.
    @parameters begin
        Kp::Real = 40.0, [description = "Proportional gain (N per m of error)"]
        Ki::Real = 80.0, [description = "Integral gain (N per m*s of error)"]
        Kd::Real = 8.0, [description = "Velocity feedback gain (N per m/s)"]
        umax::Real = 15.0, [min = 0, description = "Drive force limit (N)"]
        aw::Real = 0.0, [min = 0, max = 1, description = "Anti-windup: 1 = on, 0 = off (the bug)"]
    end
    @inputs begin
        x_ref::Real
        x::Real
        v::Real
    end
    @outputs begin
        F::Real = 0.0, [description = "Force command after the limit (N)"]
        u::Real = 0.0, [description = "PID force before the limit (N)"]
    end
    @variables begin
        k::Int = 0, [description = "Tick counter"]
        z::Real = 0.0, [description = "Integral of the position error (m*s)"]
    end
    @discrete Ts = 0.01 begin
        k += 1                                # tick counter
        err = x_ref - x                       # position error
        z += Ts * err                         # integrate the error
        u = Kp * err + Ki * z - Kd * v        # PID force, not yet limited
        F = clamp(u, -umax, umax)             # the drive saturates at +-umax
        if aw > 0.5 && abs(u) > umax
            z -= Ts * err                     # anti-windup: undo the integration
        end
    end
end
