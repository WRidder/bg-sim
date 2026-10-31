@block Ramp begin
    # From t_start, y rises from initial with slope for duration seconds, then holds
    # initial + slope*duration. The default duration (1e12 s) never ends in practice, which
    # is the ramp without saturation.
    @outputs y::Real
    @parameters begin
        t_start::Real = 0.0, [unit = "s", description = "Time at which the ramp starts"]
        slope::Real = 1.0, [unit = "1/s", description = "Rate of change of the output"]
        initial::Real = 0.0, [description = "Output value before the ramp starts"]
        duration::Real = 1.0e12, [unit = "s", min = 0, description = "Duration of the ramp; afterwards the output holds initial + slope*duration (default 1e12 s: no end)"]
    end
    @equations begin
        y ~ ifelse(
            t >= t_start,
            initial + slope * ifelse(t >= t_start + duration, duration, t - t_start),
            initial,
        )
    end
end
