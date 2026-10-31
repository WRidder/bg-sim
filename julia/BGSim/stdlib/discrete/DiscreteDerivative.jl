@block DiscreteDerivative begin
    # Backward-difference derivative (Simulink's Discrete Derivative):
    #   y[k] = gain * (u[k] - u[k-1]) / Ts,
    # the input sampled at every tick of sample_period and the output held in between. At the
    # first tick the previous sample is `initial` (set it to the starting input value for a
    # zero first output).
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Difference quotient of the last two input samples"]
    @parameters begin
        gain::Real = 1.0, [tunable = true, description = "Gain on the difference quotient"]
        initial::Real = 0.0, [description = "Input sample assumed before the first tick"]
    end
    @variables begin
        up::Real = 0.0, [description = "Input sample from the previous tick"]
        started::Int = 0, [description = "0 before the first tick, 1 afterwards"]
    end
    @discrete Ts = sample_period begin
        y = gain * (u - ifelse(started == 0, initial, up)) / Ts
        up = u
        started = 1
    end
end
