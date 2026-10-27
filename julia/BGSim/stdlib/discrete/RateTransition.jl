@block RateTransition begin
    @constants sample_period_in::Real = 5.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the input clock"]
    @constants sample_period_out::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the output clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Most recent input sample, refreshed on the output clock"]
    @variables x::Real = 0.0, [description = "Input sample taken on the input clock"]
    @discrete Ts = sample_period_in begin
        x = hold(u)
    end
    @discrete Ts = sample_period_out begin
        y = x
    end
end
