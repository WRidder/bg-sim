@block PropulsionStatus begin
    # Readouts of the propulsion (a tap: no physics). Adapted from examples/rocket (FlightStatus).
    #
    #   dv          the ideal velocity gain, the integral of T / m: in vacuum and without gravity
    #               it is Tsiolkovsky's c ln(m0 / m)
    #   tw          thrust-to-weight ratio in lunar gravity, T / (m g_moon)
    #   hover_left  how long the usable propellant would hold the vehicle in a hover at its
    #               present mass: prop c / (m g_moon)
    #   prop_pct    usable propellant left in percent of the load at the start
    @inputs begin
        m::Real, [unit = "kg"]
        T::Real, [unit = "N"]
        prop::Real, [unit = "kg", description = "Usable propellant left"]
    end
    @parameters begin
        g_moon::Real = 1.6243, [unit = "m/s^2", description = "Surface gravity mu / R^2"]
        c::Real = 2991.0, [unit = "m/s", description = "Effective exhaust velocity"]
        prop0::Real = 8000.0, [unit = "kg", description = "Usable propellant at the start"]
    end
    @variables dv_s::Real = 0.0, [unit = "m/s", state = :prefer, description = "Integral of T/m"]
    @outputs begin
        dv::Real, [unit = "m/s"]
        dv_fps::Real
        tw::Real
        hover_left::Real, [unit = "s"]
        prop_pct::Real
    end
    @equations begin
        ddt(dv_s) ~ T / m
        dv ~ dv_s
        dv_fps ~ dv_s / 0.3048
        tw ~ T / (m * g_moon)
        hover_left ~ max(prop, 0.0) * c / (m * g_moon)
        prop_pct ~ 100 * prop / prop0
    end
end
