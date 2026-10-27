@block TypeConversion begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real, [description = "Value to convert"]
    @outputs y::Real = 0.0, [description = "Converted value; a Bool signal is recorded as 1 or 0 and an Int as its integer value"]
    @parameters target::Int = 0, [options = ["Real", "Int", "Bool"], description = "Target type of the conversion"]
    @discrete Ts = sample_period begin
        if target == 1
            y = ifelse(u >= 0, floor(u), ceil(u))
        elseif target == 2
            y = ifelse(u == 0, 0.0, 1.0)
        else
            y = u
        end
    end
end
