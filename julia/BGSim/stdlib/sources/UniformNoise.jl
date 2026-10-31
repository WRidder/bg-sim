@block UniformNoise begin
    # Seeded uniform noise on a fixed clock, built like Noise: tick n (at t = n*sample_time,
    # n >= 1) draws sample n - 1 of the counter-based stream `seed` (`noise_uniform`, exact
    # and in (0, 1)), and the output y = y_min + (y_max - y_min)*u holds between ticks. Before
    # the first tick u = 1/2, so y starts at the midpoint. The sequence is a pure function of
    # (seed, sample index), bit for bit the same in simulation and in the exported C code.
    @constants sample_time::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample time of the fixed clock"]
    @outputs y::Real
    @parameters begin
        y_min::Real = -1.0, [description = "Lower bound of the noise"]
        y_max::Real = 1.0, [description = "Upper bound of the noise"]
        seed::Int = 1, [description = "Seed of the fixed pseudo-random sequence; blocks with the same seed draw the same sequence"]
    end
    @variables begin
        u::Real = 0.5, [description = "Uniform sample in (0, 1) of the last tick (1/2 before the first tick)"]
        k::Int = 0, [description = "Index of the next sample of the stream"]
    end
    @discrete Ts = sample_time begin
        u = noise_uniform(seed, k)
        k = k + 1
    end
    @equations begin
        y ~ y_min + (y_max - y_min) * u
    end
end
