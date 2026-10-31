@block ScheduledPID begin
    # Parallel PID with gains from signal inputs (gain scheduling) and a feedforward input:
    #   e = y - r                     (the ball below its setpoint asks for more current)
    #   u = ff + Kp*e + xi + Kd*d,    dxi/dt = Ki*e,    d = (e - xf)/Tf,  dxf/dt = d
    # d is the derivative of e through the first-order filter 1/(Tf*s + 1). The integral
    # accumulates Ki*e (not Ki times the integral of e), so a gain that changes with the
    # operating point does not make the output jump.
    @inputs begin
        r::Real, [unit = "m", description = "Reference (setpoint)"]
        y::Real, [unit = "m", description = "Measurement"]
        ff::Real, [unit = "A", description = "Feedforward added to the output (trim current)"]
        Kp::Real, [description = "Proportional gain (A/m)"]
        Ki::Real, [description = "Integral gain (A/(m*s))"]
        Kd::Real, [description = "Derivative gain (A*s/m)"]
    end
    @outputs u::Real, [unit = "A", description = "Controller output: feedforward plus PID"]
    @parameters Tf::Real = 0.001, [unit = "s", min = 1.0e-9, description = "Derivative filter time constant"]
    @variables begin
        e::Real = 0.0, [unit = "m", description = "Control error y - r"]
        xi::Real = 0.0, [state = :prefer, description = "Integral part of the output (A)"]
        xf::Real = 0.0, [unit = "m", state = :prefer, description = "Filtered error"]
        d::Real = 0.0, [unit = "m/s", description = "Filtered error derivative"]
    end
    @equations begin
        e ~ y - r
        ddt(xi) ~ Ki * e
        d ~ (e - xf) / Tf
        ddt(xf) ~ d
        u ~ ff + Kp * e + xi + Kd * d
    end
end
