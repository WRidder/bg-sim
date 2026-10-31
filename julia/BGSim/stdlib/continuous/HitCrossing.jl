@block HitCrossing begin
    # Detects the input crossing `level` (Simulink's Hit Crossing), located exactly as an
    # event. `n` counts the crossings in the selected direction (rising: from below the level
    # to above it; falling: from above to below; either: both), and y is 0 until the first of
    # them and 1 from that instant on. n_up and n_down count the rising and the falling
    # crossings.
    #
    # One event watches the side the input is on: `side` is 0 below the level and 1 above
    # it, and the event fires when u crosses the level away from that side, then flips it.
    # (Two mirrored events u > level and u < level would fire at the same instant and
    # chatter.) `side` starts at its start value, 0 (below) by default, as the held state of
    # Relay: set the start of `side` to 1 for an input that starts above the level, or the
    # first falling crossing is not seen.
    #
    # Note: the counters are states that only the event changes. A state whose derivative is
    # identically zero is removed by the symbolic reduction, so each carries a decay of
    # 1e-300 per second, which leaves any count unchanged in double precision.
    @inputs u::Real
    @outputs begin
        y::Real, [description = "0 before the first crossing in the selected direction, 1 from it on"]
        n::Real, [description = "Number of crossings in the selected direction"]
    end
    @parameters begin
        level::Real = 0.0, [description = "Level whose crossing is detected"]
        direction::Int = 0, [options = ["either", "rising", "falling"], description = "Crossings counted: 0 either, 1 rising, 2 falling"]
    end
    @variables begin
        side::Real = 0.0, [description = "Side of the level the input is on: 0 below, 1 above (start: the side at t = 0)"]
        n_up::Real = 0.0, [description = "Number of rising crossings"]
        n_down::Real = 0.0, [description = "Number of falling crossings"]
    end
    @equations begin
        ddt(side) ~ -1.0e-300 * side   # held (see the note above)
        ddt(n_up) ~ -1.0e-300 * n_up
        ddt(n_down) ~ -1.0e-300 * n_down
        n ~ ifelse(direction == 1, n_up, ifelse(direction == 2, n_down, n_up + n_down))
        y ~ min(n, 1.0)
    end
    @events begin
        (u - level) * (1.0 - 2.0 * side) > 0.0 => begin
            reinit(n_up, n_up + 1.0 - side)
            reinit(n_down, n_down + side)
            reinit(side, 1.0 - side)
        end
    end
end
