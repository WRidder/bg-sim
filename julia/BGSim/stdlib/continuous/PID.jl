@block PID begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        Kp::Real = 1.0, [tunable = true, description = "Proportional gain"]
        Ti::Real = 1.0, [unit = "s", min = 1.0e-9, tunable = true, description = "Integral time"]
        Td::Real = 0.01, [unit = "s", min = 1.0e-9, tunable = true, description = "Derivative time"]
        N::Real = 10.0, [min = 1.0e-9, tunable = true, description = "Derivative filter gain"]
        lower::Real = -1.0e30, [tunable = true, description = "Lower output limit (1e30 means none)"]
        upper::Real = 1.0e30, [tunable = true, description = "Upper output limit (1e30 means none)"]
    end
    @variables begin
        xi::Real = 0.0, [description = "Integral state"]
        xd::Real = 0.0, [description = "Filtered error state"]
        v::Real = 0.0, [description = "Unsaturated controller output"]
    end
    @equations begin
        v ~ Kp * u + (Kp / Ti) * xi + N * (u - xd)
        ddt(xi) ~ u / Ti + (y - v) / sqrt(Ti * Td)
        ddt(xd) ~ (u - xd) * (N / Td)
        y ~ clamp(v, lower, upper)
    end
end
