@block VariableTransportDelay begin
    # Variable transport delay y(t) = u(t - d), with the delay d given by the input `d`
    # (Simulink's Variable Transport Delay). As in TransportDelay, the input is stored at every
    # tick of sample_period in a ring buffer: the three-argument discrete `delay` intrinsic,
    # whose ring holds max_delay worth of samples and is read at a variable position with
    # linear interpolation between the stored samples.
    #
    # At each tick t_k, eb = u(t_k + sample_period - d) is read (d sampled at the tick, clamped
    # to [sample_period, max_delay]); between ticks the output interpolates linearly from the
    # previous tick's eb to this one's, so it is continuous, it equals the ideal delay for a
    # constant d and an input linear between ticks, and a change of d takes effect over one
    # sample period. Until the line has filled the output is `initial`, and the input at
    # t = 0 counts as `initial`. Simulation and the exported C code run the same ring.
    # max_delay must be a whole multiple of sample_period, at least two periods (E104).
    @constants begin
        max_delay::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Largest delay; a whole multiple of sample_period, at least 2 periods"]
        sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Period at which the input is stored and the delay sampled"]
    end
    @inputs begin
        u::Real, [description = "Signal to delay"]
        d::Real, [unit = "s", description = "Delay time, clamped to [sample_period, max_delay]"]
    end
    @outputs y::Real
    @parameters initial::Real = 0.0, [description = "Output until the delay line has filled, and the input before the first tick"]
    @variables begin
        ea::Real = 0.0, [description = "u - initial at the delay of the previous tick"]
        eb::Real = 0.0, [description = "u - initial at the delay, one sample period after the last tick"]
        tk::Real = 0.0, [unit = "s", description = "Time of the last tick"]
    end
    @discrete Ts = sample_period begin
        ea = eb
        eb = delay(u - initial, max_delay - sample_period, d - sample_period)
        tk = t
    end
    @equations begin
        y ~ initial + ea + (t - tk) / sample_period * (eb - ea)
    end
end
