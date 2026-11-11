@block VacuumGenerator begin
    # Vacuum generator (ejector or pump) on a Hydraulic port, by its suction capacity curve:
    # the free-air flow it draws out of the port falls from `Q_max` at zero vacuum to zero at
    # the maximum vacuum `dp_max`,
    #
    #   Q = u Q_max (1 - x |x|^(n - 1)) + (1 - u) G_rel (p - p_rel),   x = dp / dp_max, dp = -p,
    #
    # with `n = 1` the straight line of an ejector and `n = 2..4` the flat-then-falling curve
    # of a displacement pump (it keeps most of its flow until close to its end vacuum). The
    # control input `u` (1 = on, 0 = off) blends to the release path: a conductance `G_rel` to
    # the release pressure `p_rel` (0: vent to atmosphere, > 0: blow-off). Pressures are gauge
    # pressures (negative = vacuum), flows free-air volume flows (the datasheet unit).
    #
    # Port: `a.e` is the port pressure (taken from the network, e.g. a manifold `Volume`), `a.f`
    # the flow INTO the generator, i.e. the suction flow `Q`. Above `dp_max` the curve goes on
    # (negative flow): a network evacuated deeper than the generator can hold leaks back in.
    @ports a::Power{Hydraulic}
    @inputs u::Real, [unit = "1", description = "1 = vacuum on, 0 = release (vent or blow-off)"]
    @outputs begin
        Q::Real, [unit = "m^3/s", description = "Suction flow (free air) drawn from the port"]
        dp::Real, [unit = "Pa", description = "Vacuum level at the port (atmosphere minus port pressure)"]
    end
    @parameters begin
        dp_max::Real = 6.0e4, [unit = "Pa", min = 1.0e-6, description = "Maximum vacuum (zero flow)"]
        Q_max::Real = 5.0e-4, [unit = "m^3/s", min = 0, description = "Maximum suction flow (zero vacuum), free air"]
        n::Real = 1.0, [unit = "1", min = 1.0e-3, description = "Curve exponent: 1 = linear (ejector), 2-4 = pump-like"]
        G_rel::Real = 1.0e-7, [unit = "m^3/(s*Pa)", min = 0, description = "Release (vent / blow-off) conductance"]
        p_rel::Real = 0.0, [unit = "Pa", description = "Release pressure (0 = vent to atmosphere, > 0 = blow-off)"]
    end
    @variables begin
        x::Real = 0.0, [unit = "1", description = "Relative vacuum dp / dp_max"]
        f::Real = 1.0, [unit = "1", description = "Relative suction capacity 1 - x |x|^(n-1)"]
    end
    @equations begin
        dp ~ -a.e
        x ~ dp / dp_max
        f ~ 1 - x * (x * x + 1.0e-12)^(0.5 * (n - 1))
        Q ~ u * Q_max * f + (1 - u) * G_rel * (a.e - p_rel)
        a.f ~ Q
    end
    @orientation a => :in
end
