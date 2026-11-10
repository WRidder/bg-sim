@block Engine3D begin
    # A rocket engine on the body x axis through the centre of mass (the lunar module's thrust
    # axis), as a body wrench for an `ExternalWrenchSpatial`. The thrust follows the command
    # through a first-order lag (start-up, throttle response, tail-off) and the propellant flow
    # is thrust over the effective exhaust velocity:
    #
    #     tau dT/dt = T_cmd - T,       mdot = T / c,      c = Isp g0
    #
    # The descent engine's gimbal only trims the thrust through the centre of mass, so the
    # wrench has no moment.
    @inputs T_cmd::Real, [unit = "N", description = "Commanded thrust"]
    @parameters begin
        c::Real = 2991.0, [unit = "m/s", min = 1, description = "Effective exhaust velocity (Isp g0)"]
        tau::Real = 0.3, [unit = "s", min = 1.0e-3, description = "Thrust lag"]
    end
    @variables Tf::Real = 0.0, [unit = "N", state = :prefer, description = "Thrust (lagged)"]
    @outputs begin
        T::Real, [unit = "N"]
        mdot::Real, [unit = "kg/s"]
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @equations begin
        ddt(Tf) ~ (T_cmd - Tf) / tau
        T ~ Tf
        mdot ~ Tf / c
        fx ~ Tf
        fy ~ 0.0
        fz ~ 0.0
        tx ~ 0.0
        ty ~ 0.0
        tz ~ 0.0
    end
end
