@block Sawtooth begin
    # A periodic ramp: from t_start on, y rises linearly from offset to offset + amplitude
    # over each period and drops back to offset at every edge t_start + k*period.
    #
    # Exact periodic edges (shared by Triangle, Trapezoid and RepeatingTable). The solver
    # must locate every edge, and the edges repeat forever, so they cannot be unrolled into
    # `t >= t_start + k*period` comparisons (TimeTable's single-pass form). Three traps:
    #   * `floor(x)` adds the callback sin(pi*x), whose zero is not exact: when an edge lands
    #     on an output-grid time (period 0.1 s on a 0.01 s grid) the root cannot be consumed
    #     and the run floods with events until W206, as the trigonometric Pulse condition
    #     does (plan/STATUS.md NOTE-6 is the same failure);
    #   * `mod(x, 1)` adds no callback, but its derivative is NaN where x is an exact
    #     integer, which the adaptive solver's time gradient meets on such a grid;
    #   * a cycle-local condition such as `tau < rising` jumps at every edge, which the root
    #     finder takes for a second, spurious crossing one ulp before the real edge.
    # So each family of edges uses the signed time `t - e` to the **nearest** edge
    # e = t_start + k*period, negated for odd k: `c` below. It is continuous (a triangle
    # wave: the sign flip and the change of the nearest edge cancel half a period away from
    # the edges), its zeros are exactly the edges and nothing else, and `t - e` is an exact
    # floating-point difference, so the event condition `c > 0` has an exact zero at the
    # representable instant e. Whether t is at or after the nearest edge follows from the
    # sign of `c` and the parity `par` of k, without a comparison that jumps. k comes from
    # `mod` of x = (t - t_start)/period + phi with phi = 0.5 + 2^-20 rather than 0.5: k then
    # changes 2^-20 periods before the half-period point, so x is never an exact integer on
    # a decimal output grid (no NaN derivative), and `c` keeps its sign there.
    #
    #
    # The compiler substitutes every variable into the event conditions and flattens nested
    # sums into one sum whose order it picks, so an exact quantity must never be a bare sum:
    #   * x is a quotient, one atom wherever it appears;
    #   * k, par and e are written as 2*(0.5*a + 0.5*b): a product, so they stay atoms, and
    #     halving and doubling are exact. k = floor(x) and par (0 or 1) are exact integers,
    #     so the cycle index and the n_periods / t_start guards built from them are exact;
    #   * e is an atom, so `t - e` stays a two-term difference with its exact zero at e.
    # Without this a flattened `t - t_start - k*period` has no exact zero, and a root that
    # falls between an output-grid time and the next float floods the solver with events.
    # The C export evaluates the same expressions with the conditions frozen per step (W203).
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Height of the ramp: y rises from offset to offset + amplitude in each period"]
        period::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Period of the sawtooth"]
        offset::Real = 0.0, [description = "Output before t_start and at the start of every period"]
        t_start::Real = 0.0, [unit = "s", description = "Time of the first edge; the output is offset before it"]
    end
    @variables begin
        x::Real = 0.5, [description = "Periods since t_start, plus just over one half"]
        k::Real = 0.0, [description = "Index of the nearest edge t_start + k*period"]
        par::Real = 0.0, [description = "Parity of k: 0 for even, 1 for odd"]
        e::Real = 0.0, [unit = "s", description = "Time of the nearest edge"]
        c::Real = 0.0, [unit = "s", description = "Signed time to the nearest edge, negated for odd k; zero exactly at every edge (the event condition)"]
        cycle::Real = 0.0, [description = "Index of the current period: k at or after the nearest edge, k - 1 before it"]
    end
    @equations begin
        x ~ (t - t_start + 0.5000009536743164 * period) / period
        k ~ 2.0 * (0.5 * x - 0.5 * mod(x, 1.0))
        par ~ 2.0 * (0.5 * mod(x, 2.0) - 0.5 * mod(x, 1.0))
        e ~ 2.0 * (0.5 * t_start + 0.5 * (period * k))
        c ~ (1.0 - 2.0 * par) * (t - e)
        # c > 0: after the edge for even k, before it for odd k; c == 0: on the edge.
        cycle ~ k - 1.0 + ifelse(c > 0, 1.0 - par, ifelse(c >= 0, 1.0, par))
        y ~ offset + ifelse(
            cycle >= 0,
            amplitude * (t - e + (k - cycle) * period) / period,
            0.0,
        )
    end
end
