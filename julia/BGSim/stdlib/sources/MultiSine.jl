@block MultiSine begin
    # A sum of N sines: from t_start on,
    # y = offset + sum_i amplitudes[i]*sin(frequencies[i]*(t - t_start) + phases[i]);
    # y = offset before t_start. The frequencies are angular (rad/s), as in Sine. N is a
    # structural constant: the number of components.
    @constants N::Int = 3
    @outputs y::Real
    @parameters begin
        amplitudes::Vec{N} = [1.0, 0.5, 0.25], [description = "Amplitude of each component"]
        frequencies::Vec{N} = [1.0, 3.0, 5.0], [unit = "rad/s", description = "Angular frequency of each component (rad/s, as in Sine)"]
        phases::Vec{N} = [0.0, 0.0, 0.0], [unit = "rad", description = "Phase of each component at t_start"]
        offset::Real = 0.0, [description = "Offset; the output before t_start"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the sines start"]
    end
    @variables s::Vec{N}, [description = "Unit sine of each component"]
    @equations begin
        for i in 1:N
            s[i] ~ sin(frequencies[i] * (t - t_start) + phases[i])
        end
        y ~ offset + ifelse(t >= t_start, dot(amplitudes, s), 0.0)
    end
end
