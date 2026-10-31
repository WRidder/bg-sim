@block IntegerDelay begin
    # z^-N (J-EX9): the input sample of N ticks ago, from a ring buffer of N slots (the
    # discrete `delay` intrinsic), `initial` until N samples have arrived. N = 1 is the unit
    # delay; N = 0 passes the sample through. Bit-exact in the exported C code.
    @constants begin
        N::Int = 2, [min = 0, description = "Delay in samples"]
        sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    end
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Input sample of N ticks ago, or initial before N ticks"]
    @parameters initial::Real = 0.0, [description = "Output until N samples have arrived"]
    @discrete Ts = sample_period begin
        y = delay(u - initial, N * sample_period) + initial
    end
end
