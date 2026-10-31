@block BandLimitedWhiteNoise begin
    # Band-limited white noise as in Simulink: a seeded normal sequence on a fixed clock,
    # held between ticks and scaled to y = sqrt(noise_power/sample_time)*z, so the held
    # signal has the two-sided power spectral density noise_power (units^2/Hz) at low
    # frequencies, whatever the sample time. Choose sample_time well below the fastest
    # time constant the noise drives (Simulink suggests about 1/100 of it). The samples are
    # `noise_normal(seed, k)` as in Noise: tick n (at t = n*sample_time, n >= 1) draws sample
    # n - 1, z = 0 before the first tick, bit for bit the same in simulation and in C.
    @constants sample_time::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample time (correlation time) of the noise"]
    @outputs y::Real
    @parameters begin
        noise_power::Real = 0.1, [min = 0, description = "Height of the power spectral density (units^2/Hz); y has variance noise_power/sample_time"]
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
        y ~ sqrt(noise_power / sample_time) * z
    end
end
