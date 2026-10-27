@block OnOffDelay begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Bool, [description = "Input signal"]
    @outputs y::Bool = false, [description = "Delayed input; the start value is the state before the first tick"]
    @parameters begin
        t_on::Real = 0.0, [unit = "s", min = 0, tunable = true, description = "Time the input must stay high before the output turns on"]
        t_off::Real = 0.0, [unit = "s", min = 0, tunable = true, description = "Time the input must stay low before the output turns off"]
    end
    @variables begin
        ton::Real = 0.0, [unit = "s", description = "Time the input has been high (on-delay timer)"]
        toff::Real = 0.0, [unit = "s", description = "Time the input has been low (off-delay timer)"]
    end
    @discrete Ts = sample_period begin
        if u
            ton = ton + Ts
            toff = 0.0
            if ton >= t_on
                y = true
            end
        else
            toff = toff + Ts
            ton = 0.0
            if toff >= t_off
                y = false
            end
        end
    end
end
