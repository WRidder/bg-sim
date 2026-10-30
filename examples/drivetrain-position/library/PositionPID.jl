@block PositionPID begin
    # The textbook PID of the `naive` model, as a 1 kHz digital controller (the same rate as the
    # showcase firmware): ideal (ISA) form, filtered derivative on the measurement and
    # back-calculation anti-windup against the voltage clamp,
    #   v = Kp*e + xi - Kp*Td*N*(y - xd),   u = clamp(v, -umax, umax),
    #   xi += Ts*(Kp/Ti*e + (u - v)/Tt),    xd += (1 - exp(-N*Ts/Td))*(y - xd),   Tt = sqrt(Ti*Td).
    # The stdlib `PID` has the integral gain Kp/Ti^2 and the derivative gain Td, so the textbook
    # parameterization is kept here. `design/design.py` writes the numbers between the markers.
    @parameters begin
        # ---- GAINS (written by design/design.py) ----
        Kp::Real = 3.03, [unit = "V/rad", description = "Proportional gain"]
        Ti::Real = 0.133333333333, [unit = "s", min = 1e-6, description = "Integral time"]
        Td::Real = 0.00792079207921, [unit = "s", min = 1e-6, description = "Derivative time"]
        N::Real = 10.0, [min = 1e-6, description = "Derivative filter ratio"]
        umax::Real = 24.0, [unit = "V", min = 0.0, description = "Voltage limit"]
        # ---- END GAINS ----
    end
    @inputs begin
        r::Real
        y::Real
    end
    @outputs u::Real = 0.0, [unit = "V"]
    @variables begin
        xi::Real = 0.0, [description = "Integral state"]
        xd::Real = 0.0, [description = "Filtered measurement"]
    end
    @discrete Ts = 1e-3 begin
        e = r - y
        xd = xd + (1.0 - exp(-N * Ts / Td)) * (y - xd)
        v = Kp * e + xi - Kp * Td * N * (y - xd)
        u = clamp(v, -umax, umax)
        xi = xi + Ts * (Kp / Ti * e + (u - v) / sqrt(Ti * Td))
    end
end
