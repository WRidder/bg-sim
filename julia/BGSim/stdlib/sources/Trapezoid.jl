@block Trapezoid begin
    # Modelica.Blocks.Sources.Trapezoid: from t_start on, each period rises linearly from
    # offset to offset + amplitude over `rising`, stays high for `width`, falls back over
    # `falling` and stays at offset for the rest of the period; after n_periods periods the
    # output stays at offset (n_periods < 0: forever). Pulse is the case rising = falling = 0,
    # width = duty*period; rising + width + falling should not exceed the period.
    #
    # The four breakpoints per period are four families of exact events, built as in
    # Sawtooth and Triangle (see the comments there): `c[i]` is zero exactly at every
    # breakpoint of family i, and `a[i]` is 1 once that breakpoint has passed in the current
    # period. A zero-length ramp (rising or falling 0) makes two families coincide, which is
    # a jump; their origins `o[i]` differ only by an added zero, so the two families compute
    # the same floating-point edge and fire together.
    # The start and the end of the n_periods periods are `cycle >= 0` and
    # `cycle < n_periods`: the cycle index is an exact integer that steps exactly at the
    # period edges, so these conditions only reach zero together with the edge's own event.
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Height of the high level above offset"]
        rising::Real = 0.0, [unit = "s", min = 0, description = "Duration of the rising edge"]
        width::Real = 0.5, [unit = "s", min = 0, description = "Duration of the high level"]
        falling::Real = 0.0, [unit = "s", min = 0, description = "Duration of the falling edge"]
        period::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Period; at least rising + width + falling"]
        n_periods::Int = -1, [description = "Number of periods; a negative value repeats forever"]
        offset::Real = 0.0, [description = "Low level: the output before t_start, between the pulses and after the last period"]
        t_start::Real = 0.0, [unit = "s", description = "Start of the first rising edge"]
    end
    @variables begin
        b::Vec{4}, [unit = "s", description = "Breakpoints within a period: rise start, high start, fall start, low start"]
        o::Vec{4}, [unit = "s", description = "First breakpoint of each family: t_start + b"]
        x::Vec{4}, [description = "Periods since each family's origin, plus just over one half"]
        k::Vec{4}, [description = "Index of the nearest breakpoint of each family"]
        par::Vec{4}, [description = "Parity of k: 0 for even, 1 for odd"]
        e::Vec{4}, [unit = "s", description = "Time of the nearest breakpoint of each family"]
        c::Vec{4}, [unit = "s", description = "Signed time to the nearest breakpoint, negated for odd k; zero exactly at every breakpoint (the event condition)"]
        a::Vec{4}, [description = "1 once the breakpoint has passed in the current period, else 0"]
        cycle::Real = 0.0, [description = "Index of the current period"]
        tau::Real = 0.0, [unit = "s", description = "Time since the start of the current period"]
    end
    @equations begin
        b[1] ~ 0.0
        b[2] ~ rising
        b[3] ~ rising + width
        b[4] ~ rising + width + falling
        for i in 1:4
            o[i] ~ t_start + b[i]
            x[i] ~ (t - o[i] + 0.5000009536743164 * period) / period
            k[i] ~ 2.0 * (0.5 * x[i] - 0.5 * mod(x[i], 1.0))
            par[i] ~ 2.0 * (0.5 * mod(x[i], 2.0) - 0.5 * mod(x[i], 1.0))
            e[i] ~ 2.0 * (0.5 * o[i] + 0.5 * (period * k[i]))
            c[i] ~ (1.0 - 2.0 * par[i]) * (t - e[i])
            a[i] ~ ifelse(c[i] > 0, 1.0 - par[i], ifelse(c[i] >= 0, 1.0, par[i])) *
                   (1.0 - (k[i] - cycle)^2) + ((k[i] - cycle)^2 + k[i] - cycle) / 2.0
        end
        cycle ~ k[1] - 1.0 + ifelse(c[1] > 0, 1.0 - par[1], ifelse(c[1] >= 0, 1.0, par[1]))
        tau ~ t - e[1] + (k[1] - cycle) * period
        # rise (a[1] - a[2], a[1] = 1), high (a[2] - a[3]), fall (a[3] - a[4]), low (a[4]).
        # A zero-length ramp has a zero indicator, and max() keeps its division finite.
        y ~ offset + ifelse(
            cycle >= 0 && (n_periods < 0 || cycle < n_periods),
            amplitude * (
                (1.0 - a[2]) * tau / max(rising, 1.0e-12) + a[2] - a[3] +
                (a[3] - a[4]) * (b[4] - tau) / max(falling, 1.0e-12)
            ),
            0.0,
        )
    end
end
