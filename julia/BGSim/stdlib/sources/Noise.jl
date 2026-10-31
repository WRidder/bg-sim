@block Noise begin
    # Seeded normal noise on a fixed clock (J-EX9). Every tick draws the next sample of the
    # counter-based stream `seed` (`noise_normal`: SplitMix64 bits, an exact uniform and
    # Wichura's AS 241 normal quantile, specified in the language spec), so the sequence is a
    # pure function of (seed, sample index): it repeats bit for bit, in simulation and in the
    # exported C code. The output holds `mean + std * z` between ticks; before the first tick
    # (at t = sample_time) z is 0, so y starts at the mean.
    @constants sample_time::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample time of the fixed clock"]
    @outputs y::Real
    @parameters begin
        mean::Real = 0.0, [description = "Mean of the noise"]
        std::Real = 1.0, [min = 0, description = "Standard deviation of the noise"]
        seed::Int = 1, [description = "Seed of the fixed pseudo-random sequence; blocks with the same seed draw the same sequence"]
    end
    @variables begin
        z::Real = 0.0, [description = "Standard normal sample of the last tick (0 before the first tick)"]
        k::Int = 0, [description = "Index of the next sample of the stream"]
    end
    @discrete Ts = sample_time begin
        z = noise_normal(seed, k)
        k = k + 1
    end
    @equations begin
        y ~ mean + std * z
    end
end
