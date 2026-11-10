@block Telemetry begin
    # Read-out of the propulsion (a sensor tap, not plant physics): the totals and the
    # non-dimensional coefficients the plots, the dashboard and the checks use.
    #
    #   T          total thrust of the coaxial pair (N)
    #   P_el       electrical power into both motors (W); P_shaft the aerodynamic (shaft) power
    #   CT, CP     T / (rho A (Omega R)^2) and P_shaft / (rho A (Omega R)^3), A the area of ONE disc
    #              (the convention of Koning et al. 2019), Omega the lower rotor's speed
    #   coll_*_deg the collectives the swashplates set, cyc_deg the cyclic amplitude (lower rotor)
    @inputs begin
        Tu::Real
        Tl::Real
        Pu::Real
        Pl::Real
        Pu_el::Real
        Pl_el::Real
        th_u::Real
        th_l::Real
        cx::Real
        cy::Real
        speed_rpm::Real
    end
    @outputs begin
        T::Real, [unit = "N"]
        P_el::Real, [unit = "W"]
        P_shaft::Real, [unit = "W"]
        CT::Real
        CP::Real
        coll_u_deg::Real, [unit = "deg"]
        coll_l_deg::Real, [unit = "deg"]
        cyc_deg::Real, [unit = "deg"]
    end
    @parameters begin
        rho::Real = 0.0165, [unit = "kg/m^3"]
        R::Real = 0.605, [unit = "m"]
        k_w::Real = 0.10471975511965977, [unit = "1/s", description = "rad/s per rpm"]
    end
    @variables vt::Real = 160.0, [unit = "m/s", description = "Tip speed"]
    @equations begin
        T ~ Tu + Tl
        P_el ~ Pu_el + Pl_el
        P_shaft ~ Pu + Pl
        vt ~ speed_rpm * k_w * R
        CT ~ T / (rho * 3.141592653589793 * R * R * vt * vt + 1.0e-9)
        CP ~ (Pu + Pl) / (rho * 3.141592653589793 * R * R * vt * vt * vt + 1.0e-9)
        coll_u_deg ~ 57.29577951308232 * th_u
        coll_l_deg ~ 57.29577951308232 * th_l
        cyc_deg ~ 57.29577951308232 * sqrt(cx * cx + cy * cy)
    end
end
