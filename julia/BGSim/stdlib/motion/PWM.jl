@block PWM begin
    # Pulse-width modulation with a sawtooth carrier (natural sampling, as Simulink's PWM
    # Generator and 20-sim's PWM block): from t_start, every carrier period T = 1/frequency
    # starts high and switches low after the fraction d = clamp(u, 0, 1) of the period, so
    # the output is `high` while the carrier phase is below the duty input and `low`
    # otherwise. d = 0 is always low and d = 1 always high; the mean over a period is
    # low + (high - low)*d, which PWMAverage outputs directly. Before t_start the output is
    # `low`. Every edge is one event of the variable-step solver, so a fast carrier over a
    # long run needs a raised event limit; use PWMAverage for an averaged model.
    #
    # Exact edges, built as in sources/Trapezoid (see the comments there and in Sawtooth):
    # family 1 is the rising edges t_start + k*T, family 2 the falling edges t_start + d*T +
    # k*T. Per family, `c[i]` is the signed time to the nearest edge, negated for odd k, so
    # its zeros are exactly the edges, and `a[2]` is 1 once this period's falling edge has
    # passed. A duty input that varies moves the family-2 origin, which keeps `c[2]`
    # continuous: the edge is then the crossing of the carrier phase and the duty. With
    # d = 0 both origins are the same float, so the two edges fire together.
    @inputs u::Real, [description = "Duty cycle, 0..1 (clamped)"]
    @outputs y::Real, [description = "Switched output: high or low"]
    @parameters begin
        frequency::Real = 1000.0, [unit = "Hz", min = 1.0e-12, description = "Carrier (switching) frequency"]
        high::Real = 1.0, [description = "Output while the switch is on"]
        low::Real = 0.0, [description = "Output while the switch is off, and before t_start"]
        t_start::Real = 0.0, [unit = "s", description = "Time of the first rising edge"]
    end
    @variables begin
        period::Real = 1.0e-3, [unit = "s", description = "Carrier period, 1/frequency"]
        d::Real = 0.0, [description = "Duty cycle, clamped to 0..1"]
        o::Vec{2}, [unit = "s", description = "First edge of each family: t_start (rising) and t_start + d*period (falling)"]
        x::Vec{2}, [description = "Periods since each family's origin, plus just over one half"]
        k::Vec{2}, [description = "Index of the nearest edge of each family"]
        par::Vec{2}, [description = "Parity of k: 0 for even, 1 for odd"]
        e::Vec{2}, [unit = "s", description = "Time of the nearest edge of each family"]
        c::Vec{2}, [unit = "s", description = "Signed time to the nearest edge, negated for odd k; zero exactly at every edge (the event condition)"]
        cycle::Real = 0.0, [description = "Index of the current carrier period"]
        off::Real = 0.0, [description = "1 once the falling edge of the current period has passed, else 0"]
    end
    @equations begin
        period ~ 1.0 / frequency
        d ~ clamp(u, 0.0, 1.0)
        o[1] ~ t_start + 0.0
        o[2] ~ t_start + d * period
        for i in 1:2
            x[i] ~ (t - o[i] + 0.5000009536743164 * period) / period
            k[i] ~ 2.0 * (0.5 * x[i] - 0.5 * mod(x[i], 1.0))
            par[i] ~ 2.0 * (0.5 * mod(x[i], 2.0) - 0.5 * mod(x[i], 1.0))
            e[i] ~ 2.0 * (0.5 * o[i] + 0.5 * (period * k[i]))
            c[i] ~ (1.0 - 2.0 * par[i]) * (t - e[i])
        end
        cycle ~ k[1] - 1.0 + ifelse(c[1] > 0, 1.0 - par[1], ifelse(c[1] >= 0, 1.0, par[1]))
        off ~ ifelse(c[2] > 0, 1.0 - par[2], ifelse(c[2] >= 0, 1.0, par[2])) *
              (1.0 - (k[2] - cycle)^2) + ((k[2] - cycle)^2 + k[2] - cycle) / 2.0
        y ~ low + ifelse(cycle >= 0, (high - low) * (1.0 - off), 0.0)
    end
end
