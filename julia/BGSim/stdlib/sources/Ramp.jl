@block Ramp begin
    @outputs y::Real
    @parameters begin
        t_start::Real = 0.0, [unit = "s", description = "Time at which the ramp starts"]
        slope::Real = 1.0, [unit = "1/s", description = "Rate of change of the output"]
        initial::Real = 0.0, [description = "Output value before the ramp starts"]
    end
    @equations y ~ ifelse(t >= t_start, initial + slope * (t - t_start), initial)
end
