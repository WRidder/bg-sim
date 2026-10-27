@block UnitDelay begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Input value from the previous tick, or initial at the first tick"]
    @parameters initial::Real = 0.0, [tunable = true, description = "Output value at the first tick (the state before it)"]
    @variables begin
        x::Real = 0.0, [description = "Input sample from the previous tick"]
        started::Int = 0, [description = "0 before the first tick, 1 afterwards"]
    end
    @discrete Ts = sample_period begin
        y = ifelse(started == 0, initial, x)
        x = u
        started = 1
    end
end
