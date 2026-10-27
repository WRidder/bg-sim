@block DiscretePID begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real, [description = "Control error"]
    @outputs y::Real = 0.0, [description = "Controller output, clamped to the limits"]
    @parameters begin
        method::Int = 1, [options = ["forward", "backward", "trapezoidal"], description = "Discretization of the integral term"]
        Kp::Real = 1.0, [tunable = true, description = "Proportional gain"]
        Ti::Real = 1.0, [unit = "s", min = 1.0e-9, tunable = true, description = "Integral time"]
        Td::Real = 0.01, [unit = "s", min = 0, tunable = true, description = "Derivative time"]
        lower::Real = -1.0e30, [tunable = true, description = "Lower output limit (1e30 means none)"]
        upper::Real = 1.0e30, [tunable = true, description = "Upper output limit (1e30 means none)"]
    end
    @variables begin
        i::Real = 0.0, [description = "Integral of the error, in error-seconds"]
        ep::Real = 0.0, [description = "Error from the previous tick"]
    end
    @discrete Ts = sample_period begin
        if method == 0
            delta = Ts * ep
        elseif method == 1
            delta = Ts * u
        else
            delta = Ts * (u + ep) / 2.0
        end
        i = i + delta
        d = (u - ep) / Ts
        v = Kp * u + (Kp / Ti) * i + (Kp * Td) * d
        if v > upper
            i = i - delta
            v = Kp * u + (Kp / Ti) * i + (Kp * Td) * d
        elseif v < lower
            i = i - delta
            v = Kp * u + (Kp / Ti) * i + (Kp * Td) * d
        end
        y = clamp(v, lower, upper)
        ep = u
    end
end
