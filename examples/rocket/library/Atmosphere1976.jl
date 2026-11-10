@block Atmosphere1976 begin
    # U.S. Standard Atmosphere 1976 as a table: pressure, density, temperature and speed of sound
    # at a geometric altitude. The breakpoints (written by design/build_model.py from
    # design/data.py) are every kilometre up to 86 km, computed from the US76 layer constants,
    # and the standard's tabulated values from 90 to 300 km. ln(p) and ln(rho) are interpolated
    # linearly, which is exact inside an isothermal layer and within 0.01 % elsewhere; above the
    # last breakpoint the values are held. The speed of sound uses gamma = 1.4 and
    # R = 287.0528 J/(kg K); above about 86 km it is a formal value (the air is no continuum).
    @constants N::Int = 2, [min = 2, description = "Number of breakpoints"]
    @inputs h::Real, [unit = "m", description = "Geometric altitude"]
    @outputs begin
        p::Real, [unit = "Pa"]
        rho::Real, [unit = "kg/m^3"]
        T::Real, [unit = "K"]
        a::Real, [unit = "m/s"]
    end
    @parameters begin
        h_tab::Vec{N} = [0.0, 11000.0], [unit = "m", description = "Altitude breakpoints"]
        T_tab::Vec{N} = [288.15, 216.65], [unit = "K", description = "Temperature"]
        lnp_tab::Vec{N} = [11.526, 10.0973], [description = "ln(p / 1 Pa)"]
        lnrho_tab::Vec{N} = [0.2029, -1.0237], [description = "ln(rho / 1 kg/m^3)"]
        scale::Real = 1.0, [min = 0, description = "Multiplier on p and rho (0: vacuum)"]
        p_ref::Real = 1.0, [unit = "Pa", description = "Unit of the ln(p) table"]
        rho_ref::Real = 1.0, [unit = "kg/m^3", description = "Unit of the ln(rho) table"]
        gamma_R::Real = 401.87392, [unit = "m^2/(s^2*K)", description = "gamma R of air: 1.4 * 287.0528"]
    end
    @equations begin
        p ~ scale * p_ref * exp(interp1(h, h_tab, lnp_tab))
        rho ~ scale * rho_ref * exp(interp1(h, h_tab, lnrho_tab))
        T ~ interp1(h, h_tab, T_tab)
        a ~ sqrt(gamma_R * T)
    end
end
