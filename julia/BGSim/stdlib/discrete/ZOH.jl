@block ZOH begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Sample of the input, held between ticks"]
    @discrete Ts = sample_period begin
        y = hold(u)
    end
end
