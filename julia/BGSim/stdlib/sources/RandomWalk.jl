@block RandomWalk begin
    # A seeded Gaussian random walk on a fixed clock: every tick adds step_std*z to the sum,
    # with z = noise_normal(seed, k) the next sample of the counter-based stream, and the
    # output y = initial + w holds between ticks. Tick n (at t = n*sample_time, n >= 1) adds
    # step n, so y = initial before the first tick and the variance after n ticks is
    # n*step_std^2 (a Wiener process with diffusion step_std^2/sample_time when sampled).
    # The sum runs in the same order in simulation and in the exported C code, so the walk
    # is bit for bit the same.
    @constants sample_time::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample time of the fixed clock"]
    @outputs y::Real
    @parameters begin
        step_std::Real = 1.0e-2, [min = 0, description = "Standard deviation of each step"]
        initial::Real = 0.0, [description = "Output before the first step"]
        seed::Int = 1, [description = "Seed of the fixed pseudo-random sequence; blocks with the same seed draw the same sequence"]
    end
    @variables begin
        w::Real = 0.0, [description = "Sum of the steps so far"]
        k::Int = 0, [description = "Index of the next sample of the stream"]
    end
    @discrete Ts = sample_time begin
        w = w + step_std * noise_normal(seed, k)
        k = k + 1
    end
    @equations begin
        y ~ initial + w
    end
end
