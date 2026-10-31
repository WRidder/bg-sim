@block PRBS begin
    # A pseudo-random binary sequence for system identification: the output switches
    # between offset - amplitude and offset + amplitude, choosing the level afresh every
    # `bit_ticks` ticks of the clock (the minimum dwell is bit_ticks*sample_time). Each choice is
    # `noise_uniform(seed, j) < 1/2` for the j-th choice (j = 0, 1, ...), a fair coin from the
    # counter-based stream, so the sequence is a pure function of the seed, bit for bit the
    # same in simulation and in the exported C code. This is a random binary signal, not a
    # maximal-length shift-register sequence: it does not repeat with a fixed period.
    # As in Noise, the clock ticks at t = n*sample_time, n >= 1: the first tick draws bit 0,
    # and bit j is drawn at tick 1 + j*bit_ticks. Before the first tick y = offset.
    @constants sample_time::Real = 1.0e-2, [unit = "s", min = 1.0e-12, description = "Sample time of the clock; the level can change only at its ticks"]
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Half the distance between the two levels"]
        offset::Real = 0.0, [description = "Mean of the two levels"]
        bit_ticks::Int = 1, [min = 1, description = "Number of ticks each level is held at least (the bit length)"]
        seed::Int = 1, [description = "Seed of the fixed pseudo-random sequence; blocks with the same seed draw the same sequence"]
    end
    @variables begin
        s::Real = 0.0, [description = "Level of the current bit, -1 or 1 (0 until the first draw)"]
        j::Int = 0, [description = "Index of the next bit of the stream"]
        n::Int = 0, [description = "Ticks left before the next bit"]
    end
    @discrete Ts = sample_time begin
        n = n - 1
        if n <= 0
            s = ifelse(noise_uniform(seed, j) < 0.5, -1.0, 1.0)
            j = j + 1
            n = bit_ticks
        end
    end
    @equations begin
        y ~ offset + amplitude * s
    end
end
