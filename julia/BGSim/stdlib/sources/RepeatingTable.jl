@block RepeatingTable begin
    # TimeTable played periodically: the N values are spaced sample_time apart from t_start
    # and repeat with the period N*sample_time. Hold keeps value i for one sample; linear
    # interpolates from value i to value i + 1 and, over the last sample, from value N back
    # to value 1, so the repeated signal is continuous. Before t_start the output is
    # values[1], as in TimeTable. N must be at least 3.
    #
    # Every sample instant is a family of exact events, built as in Sawtooth and Trapezoid
    # (see the comments there): `c[i]` is zero exactly at every repetition of sample i, and
    # `a[i]` is 1 once sample i has passed in the current period. The sum of the `a[i]` is
    # then the index of the current sample, so hold reads the table exactly at that sample;
    # linear reads it at the time `tau` within the period and adds the wrap from value N to
    # value 1. Both go through `interp1` on the sample times `xs`, so no table index is ever
    # computed at run time. Hold and linear are a weighted sum, as in TimeTable.
    @constants N::Int = 8
    @outputs y::Real
    @parameters begin
        t_start::Real = 0.0, [unit = "s", description = "Time of the first table value"]
        sample_time::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Spacing of the table samples; the period is N*sample_time"]
        values::Vec{N} = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0], [description = "Output value at each sample of one period"]
        method::Int = 1, [options = ["hold", "linear"], description = "Interpolation: 0 = hold, 1 = linear (value N back to value 1 over the last sample)"]
    end
    @variables begin
        xs::Vec{N}, [unit = "s", description = "Sample times within a period"]
        x::Vec{N}, [description = "Periods since each sample's first instant, plus just over one half"]
        k::Vec{N}, [description = "Index of the nearest repetition of each sample"]
        par::Vec{N}, [description = "Parity of k: 0 for even, 1 for odd"]
        e::Vec{N}, [unit = "s", description = "Time of the nearest repetition of each sample"]
        c::Vec{N}, [unit = "s", description = "Signed time to the nearest repetition of each sample, negated for odd k; zero exactly at every sample (the event condition)"]
        a::Vec{N}, [description = "1 once the sample has passed in the current period, else 0"]
        cycle::Real = 0.0, [description = "Index of the current period"]
        tau::Real = 0.0, [unit = "s", description = "Time since the start of the current period"]
    end
    @equations begin
        for i in 1:N
            xs[i] ~ (i - 1) * sample_time
            x[i] ~ (t - t_start - xs[i] + 0.5000009536743164 * (N * sample_time)) /
                   (N * sample_time)
            k[i] ~ 2.0 * (0.5 * x[i] - 0.5 * mod(x[i], 1.0))
            par[i] ~ 2.0 * (0.5 * mod(x[i], 2.0) - 0.5 * mod(x[i], 1.0))
            e[i] ~ 2.0 * (0.5 * (t_start + xs[i]) + 0.5 * ((N * sample_time) * k[i]))
            c[i] ~ (1.0 - 2.0 * par[i]) * (t - e[i])
            a[i] ~ ifelse(c[i] > 0, 1.0 - par[i], ifelse(c[i] >= 0, 1.0, par[i])) *
                   (1.0 - (k[i] - cycle)^2) + ((k[i] - cycle)^2 + k[i] - cycle) / 2.0
        end
        cycle ~ k[1] - 1.0 + ifelse(c[1] > 0, 1.0 - par[1], ifelse(c[1] >= 0, 1.0, par[1]))
        tau ~ t - e[1] + (k[1] - cycle) * (N * sample_time)
        y ~ ifelse(
            cycle >= 0,
            (1 - method) * interp1((dot(a, a) - 1.0) * sample_time, xs, values) +
            method * (
                interp1(tau, xs, values) +
                a[N] * (values[1] - values[N]) * (tau - xs[N]) / sample_time
            ),
            values[1],
        )
    end
end
