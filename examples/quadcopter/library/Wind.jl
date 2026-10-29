@block Wind begin
    # Wind gust generator: a mean wind plus a new Gaussian gust every `Ts` = 0.5 s (a fixed
    # pseudo-random sequence, `seed`), world frame, horizontal only. The stepped output is smoothed by a
    # `Gust` lag before it reaches the airframe. It is a discrete block because the stdlib `Noise` is a
    # function of `t` through `floor`, whose staircase makes the solver chase a root at every step and,
    # at some step times, never converge (the W206 event limit).
    @outputs begin
        wind::Vec{3} = [0.0, 0.0, 0.0]
    end
    @parameters begin
        mean::Vec{3} = [0.4, -0.2, 0.0], [unit = "m/s", description = "Mean wind (world x, y, z)"]
        sigma::Real = 0.5, [unit = "m/s", min = 0, description = "Standard deviation of a gust (horizontal)"]
        seed::Real = 11.0, [description = "Sequence selector"]
    end
    @variables k::Real = 0.0, [description = "Gust counter"]
    @discrete Ts = 0.5 begin
        k = k + 1.0
        r = [0.0, 0.0]
        for j in 1:2
            u1 = mod(sin(seed * 12.9898 + k * 78.233 + j * 37.719) * 43758.5453, 1.0) + 1.0e-12
            u2 = mod(sin(seed * 39.3468 + k * 11.135 + j * 93.989) * 24634.6345, 1.0)
            r[j] = sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
        end
        wind = mean + sigma * [r[1], r[2], 0.0]
    end
end
