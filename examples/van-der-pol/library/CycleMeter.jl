@block CycleMeter begin
    # Measures a self-excited oscillation cycle by cycle, with events (located exactly):
    # * a cycle starts at every upward zero crossing of u: T is the time between the last two,
    #   f = f_scale/T, T_s = w0*T the period in scaled time;
    # * amp is the last maximum of u, taken where du (any signal with the sign of du/dt, e.g. the
    #   second state) crosses zero downward;
    # * dw1 and dw2 are the changes of the accumulated inputs w1 and w2 over the last full cycle
    #   (energy per cycle).
    # Each of the two watched signals has a held `side` (0 below zero, 1 above), as in the stdlib
    # HitCrossing: set its start to 1 for a signal that starts above zero. The outputs are 0
    # until the first full cycle (two upward crossings) has been seen.
    @inputs begin
        u::Real, [description = "Oscillating signal"]
        du::Real, [description = "Signal with the sign of du/dt"]
        w1::Real, [description = "First accumulated quantity (e.g. an energy integral)"]
        w2::Real, [description = "Second accumulated quantity"]
    end
    @outputs begin
        T::Real, [description = "Period: time between the last two upward zero crossings of u"]
        f::Real, [description = "Frequency f_scale/T"]
        T_s::Real, [description = "Scaled period w0*T"]
        amp::Real, [description = "Last maximum of u"]
        n::Real, [description = "Number of upward zero crossings of u so far"]
        dw1::Real, [description = "Change of w1 over the last full cycle"]
        dw2::Real, [description = "Change of w2 over the last full cycle"]
    end
    @parameters begin
        w0::Real = 1.0, [min = 0, description = "Time scale of T_s = w0*T (1: T_s = T)"]
        f_scale::Real = 1.0, [min = 0, description = "Unit factor of f = f_scale/T (1: Hz, 1e-6: MHz)"]
    end
    @variables begin
        side::Real = 0.0, [description = "Side of zero u is on: 0 below, 1 above (start: the side at t = 0)"]
        dside::Real = 0.0, [description = "Side of zero du is on (start: the side at t = 0)"]
        t_up::Real = 0.0, [description = "Time of the last upward crossing"]
        Tv::Real = 0.0, [description = "Held period"]
        Av::Real = 0.0, [description = "Held amplitude"]
        nv::Real = 0.0, [description = "Held crossing count"]
        w1_up::Real = 0.0, [description = "w1 at the last upward crossing"]
        w2_up::Real = 0.0, [description = "w2 at the last upward crossing"]
        d1::Real = 0.0, [description = "Held change of w1 per cycle"]
        d2::Real = 0.0, [description = "Held change of w2 per cycle"]
    end
    @equations begin
        ddt(side) ~ 0.0   # held: only the events change these
        ddt(dside) ~ 0.0
        ddt(t_up) ~ 0.0
        ddt(Tv) ~ 0.0
        ddt(Av) ~ 0.0
        ddt(nv) ~ 0.0
        ddt(w1_up) ~ 0.0
        ddt(w2_up) ~ 0.0
        ddt(d1) ~ 0.0
        ddt(d2) ~ 0.0
        T ~ Tv
        f ~ ifelse(Tv > 0.0, f_scale / max(Tv, 1.0e-300), 0.0)
        T_s ~ w0 * Tv
        amp ~ Av
        n ~ nv
        dw1 ~ d1
        dw2 ~ d2
    end
    @events begin
        u * (1.0 - 2.0 * side) > 0.0 => begin
            # u leaves its side; side == 0 means an upward crossing (a new cycle)
            reinit(Tv, ifelse(side < 0.5 && nv > 0.5, t - t_up, Tv))
            reinit(d1, ifelse(side < 0.5 && nv > 0.5, w1 - w1_up, d1))
            reinit(d2, ifelse(side < 0.5 && nv > 0.5, w2 - w2_up, d2))
            reinit(t_up, ifelse(side < 0.5, t, t_up))
            reinit(w1_up, ifelse(side < 0.5, w1, w1_up))
            reinit(w2_up, ifelse(side < 0.5, w2, w2_up))
            reinit(nv, nv + 1.0 - side)
            reinit(side, 1.0 - side)
        end
        du * (1.0 - 2.0 * dside) > 0.0 => begin
            # du leaves its side; dside == 1 means du falls through zero: a maximum of u
            reinit(Av, ifelse(dside > 0.5, u, Av))
            reinit(dside, 1.0 - dside)
        end
    end
end
