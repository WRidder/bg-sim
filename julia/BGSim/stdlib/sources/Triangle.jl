@block Triangle begin
    # A periodic triangle: from t_start on, y rises linearly from offset to offset +
    # amplitude over the first half of each period and falls back over the second half.
    #
    # The two kinks per period (t_start + k*period and half a period later) are two families
    # of exact events, built as in Sawtooth (see the comment there): per family i, `c[i]` is
    # the signed time to the nearest kink e[i], negated for odd k, so its zeros are exactly
    # the kinks. The peak is reached once the second family's kink of the current period has
    # passed: its nearest kink lies in the current period (d = 0), in the next one (d = 1,
    # so this period's kink has passed) or in the previous one (d = -1, not yet), and
    # `after*(1 - d^2) + (d^2 + d)/2` picks the answer from small integers, exactly, without
    # a comparison that jumps.
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Height of the peak above offset, reached half a period after each start"]
        period::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Period of the triangle"]
        offset::Real = 0.0, [description = "Output before t_start and at the start of every period"]
        t_start::Real = 0.0, [unit = "s", description = "Start of the first period; the output is offset before it"]
    end
    @variables begin
        x::Vec{2}, [description = "Periods since each kink family's origin, plus just over one half"]
        k::Vec{2}, [description = "Index of the nearest kink of each family"]
        par::Vec{2}, [description = "Parity of k: 0 for even, 1 for odd"]
        e::Vec{2}, [unit = "s", description = "Time of the nearest kink of each family"]
        c::Vec{2}, [unit = "s", description = "Signed time to the nearest kink, negated for odd k; zero exactly at every kink (the event condition)"]
        cycle::Real = 0.0, [description = "Index of the current period"]
        tau::Real = 0.0, [unit = "s", description = "Time since the start of the current period"]
    end
    @equations begin
        for i in 1:2
            x[i] ~ (t - t_start - 0.5 * (i - 1) * period + 0.5000009536743164 * period) / period
            k[i] ~ 2.0 * (0.5 * x[i] - 0.5 * mod(x[i], 1.0))
            par[i] ~ 2.0 * (0.5 * mod(x[i], 2.0) - 0.5 * mod(x[i], 1.0))
            e[i] ~ 2.0 * (0.5 * (t_start + 0.5 * (i - 1) * period) + 0.5 * (period * k[i]))
            c[i] ~ (1.0 - 2.0 * par[i]) * (t - e[i])
        end
        cycle ~ k[1] - 1.0 + ifelse(c[1] > 0, 1.0 - par[1], ifelse(c[1] >= 0, 1.0, par[1]))
        tau ~ t - e[1] + (k[1] - cycle) * period
        # Rising while the peak of this period has not passed, falling afterwards.
        y ~ offset + ifelse(
            cycle >= 0,
            amplitude * 2.0 * (
                tau + (
                    ifelse(c[2] > 0, 1.0 - par[2], ifelse(c[2] >= 0, 1.0, par[2])) *
                    (1.0 - (k[2] - cycle)^2) + ((k[2] - cycle)^2 + k[2] - cycle) / 2.0
                ) * (period - 2.0 * tau)
            ) / period,
            0.0,
        )
    end
end
