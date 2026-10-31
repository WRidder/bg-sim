@block TransportDelay begin
    # Constant transport delay y(t) = u(t - delay_time) (J-EX9). The input is stored at every
    # tick of `sample_period` in a ring buffer (the discrete `delay` intrinsic) and the output
    # interpolates linearly between the two stored samples around t - delay_time, so it is
    # continuous and exact for an input that is linear between ticks; otherwise the error is
    # at most sample_period^2 / 8 * max|u''|. Simulation and the exported C code run the same
    # buffer and the same interpolation. Until the line has filled (t < delay_time) the output
    # is `initial`; the input at t = 0 counts as `initial` (the first sample is the first tick).
    # delay_time must be a whole multiple of sample_period, at least one period (E104).
    @constants begin
        delay_time::Real = 0.1, [unit = "s", min = 1.0e-12, description = "Delay T, a whole multiple of sample_period"]
        sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Period at which the input is stored"]
    end
    @inputs u::Real
    @outputs y::Real
    @parameters initial::Real = 0.0, [description = "Output until the delay line has filled, and the input before the first tick"]
    @variables begin
        ea::Real = 0.0, [description = "u - initial at delay_time before the last tick"]
        eb::Real = 0.0, [description = "u - initial at delay_time - sample_period before the last tick"]
        tk::Real = 0.0, [unit = "s", description = "Time of the last tick"]
    end
    @discrete Ts = sample_period begin
        ea = eb
        eb = delay(u - initial, delay_time - sample_period)
        tk = t
    end
    @equations begin
        y ~ initial + ea + (t - tk) / sample_period * (eb - ea)
    end
end
