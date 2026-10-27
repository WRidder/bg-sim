@block Counter begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs begin
        trigger::Bool, [description = "Counts one step on every rising edge"]
        reset::Bool, [description = "Resets the count to lower while high"]
    end
    @outputs y::Int = 0, [description = "Current count"]
    @parameters begin
        lower::Int = 0, [description = "Count after a reset and the wrap target"]
        upper::Int = 10, [description = "Largest count before a wrap or a stop"]
        step::Int = 1, [description = "Increment per rising edge"]
        wrap::Int = 1, [options = ["stop", "wrap"], description = "What happens above upper: wrap to lower, or stop at upper"]
    end
    @variables begin
        tp::Bool = false, [description = "Trigger sample from the previous tick"]
        started::Int = 0, [description = "0 before the first tick, 1 afterwards"]
    end
    @discrete Ts = sample_period begin
        if started == 0
            y = lower
            started = 1
        elseif reset
            y = lower
        else
            if trigger
                if !tp
                    if y + step > upper
                        if wrap == 1
                            y = lower
                        else
                            y = upper
                        end
                    else
                        y = y + step
                    end
                end
            end
        end
        tp = trigger
    end
end
