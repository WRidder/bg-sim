@block DiscreteIntegrator begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Integral of the input, clamped to the limits"]
    @parameters begin
        method::Int = 1, [options = ["forward", "backward", "trapezoidal"], description = "Integration method"]
        lower::Real = -1.0e30, [tunable = true, description = "Lower output limit (1e30 means none)"]
        upper::Real = 1.0e30, [tunable = true, description = "Upper output limit (1e30 means none)"]
    end
    @variables begin
        i::Real = 0.0, [description = "Integral state, before the output limits"]
        up::Real = 0.0, [description = "Input sample from the previous tick"]
    end
    @discrete Ts = sample_period begin
        if method == 0
            i = i + Ts * up
        elseif method == 1
            i = i + Ts * u
        else
            i = i + Ts * (u + up) / 2.0
        end
        y = clamp(i, lower, upper)
        up = u
    end
end
