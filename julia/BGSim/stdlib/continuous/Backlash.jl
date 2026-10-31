@block Backlash begin
    # Signal backlash (play, Simulink's Backlash): the output moves only when the input pushes
    # it, from either end of a deadband `width` wide centred on the output; inside the band
    # the output holds. In each direction y = u -/+ width/2 while the input drives it.
    #
    # Realisation: the held position s is updated at every tick of sample_period,
    #   s = clamp(s, u - width/2, u + width/2),
    # and the output y = clamp(s, u - width/2, u + width/2) is continuous, so the engaged
    # output follows the input exactly between ticks and stays continuous at the ticks. When
    # the input reverses between two ticks the output follows it back until the next tick
    # (the error is at most the input's travel in one sample period); a shorter sample_period
    # makes the hold exact. Before the first tick s is `initial`.
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Period at which the held position is updated"]
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        width::Real = 1.0, [min = 0, description = "Deadband width: the total play between the two contact points"]
        initial::Real = 0.0, [description = "Held output position at the start (clamped into u -/+ width/2)"]
    end
    @variables begin
        s::Real = 0.0, [description = "Held output position, updated every tick"]
        started::Real = 0.0, [description = "0 before the first tick, 1 afterwards"]
    end
    @discrete Ts = sample_period begin
        s = clamp(ifelse(started > 0.5, s, initial), u - 0.5 * width, u + 0.5 * width)
        started = 1.0
    end
    @equations begin
        y ~ clamp(ifelse(started > 0.5, s, initial), u - 0.5 * width, u + 0.5 * width)
    end
end
