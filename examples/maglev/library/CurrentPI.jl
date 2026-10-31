@block CurrentPI begin
    # Inner current loop of the bond-graph maglev: a PI controller from the current setpoint
    # and the measured coil current to the amplifier voltage command, with output limits and
    # back-calculation anti-windup:
    #   e = i_ref - i,   v_u = Kp*(e + x),   v = clamp(v_u, -v_max, v_max),
    #   dx/dt = e/Ti + (v - v_u)/(Kp*Ti)
    # With Kp = L*w_i and Ti = L/R the PI zero cancels the coil pole R/L and the current
    # follows its setpoint as w_i/(s + w_i).
    @inputs begin
        i_ref::Real, [unit = "A", description = "Current setpoint"]
        i::Real, [unit = "A", description = "Measured coil current"]
    end
    @outputs v::Real, [unit = "V", description = "Voltage command to the amplifier"]
    @parameters begin
        Kp::Real = 30.0, [unit = "V/A", min = 0, description = "Proportional gain"]
        Ti::Real = 0.015, [unit = "s", min = 1.0e-9, description = "Integral time"]
        v_max::Real = 60.0, [unit = "V", min = 0, description = "Output limit (the amplifier rail)"]
    end
    @variables begin
        x::Real = 0.0, [unit = "A", state = :prefer, description = "Integral state (in current units)"]
        v_u::Real = 0.0, [unit = "V", description = "Unlimited output"]
    end
    @equations begin
        v_u ~ Kp * (i_ref - i + x)
        v ~ clamp(v_u, -v_max, v_max)
        ddt(x) ~ (i_ref - i) / Ti + (v - v_u) / (Kp * Ti)
    end
end
