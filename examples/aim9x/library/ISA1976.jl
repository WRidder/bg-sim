@block ISA1976 begin
    # U.S. Standard Atmosphere 1976, troposphere and lower stratosphere (0 to 20 km). A signal
    # block: it computes the air the airframe flies through, it adds no physics to the graph.
    #
    #   T      temperature (K), 288.15 - 0.0065 h below 11 km, 216.65 K above
    #   p      static pressure (Pa), the polytropic law below 11 km, the isothermal law above
    #   rho    density p/(R T)
    #   a      speed of sound sqrt(gamma R T)
    #
    # `scale` multiplies p and rho (0: vacuum for a vacuum check). The table holds the edge
    # values outside [-1 km, 20 km].
    @inputs h::Real, [unit = "m", description = "Geometric altitude"]
    @parameters begin
        scale::Real = 1.0, [min = 0, description = "Multiplier on pressure and density (0: vacuum)"]
        h_min::Real = -1000.0, [unit = "m", description = "Lower end of the table"]
        h_max::Real = 20000.0, [unit = "m", description = "Upper end of the table"]
        h_trop::Real = 11000.0, [unit = "m", description = "Tropopause"]
        t0::Real = 288.15, [unit = "K", description = "Sea-level temperature"]
        p0::Real = 101325.0, [unit = "Pa", description = "Sea-level pressure"]
        p_trop::Real = 22632.06, [unit = "Pa", description = "Pressure at the tropopause"]
        t_trop::Real = 216.65, [unit = "K", description = "Tropopause temperature"]
        lapse::Real = 0.0065, [unit = "K/m", description = "Tropospheric lapse rate"]
        g0::Real = 9.80665, [unit = "m/s^2", description = "Gravitational acceleration"]
        r_air::Real = 287.05287, [unit = "J/(kg*K)", description = "Specific gas constant of air"]
        gamma_air::Real = 1.4, [description = "Ratio of specific heats"]
    end
    @variables begin
        hc::Real = 0.0, [unit = "m", description = "Clamped altitude"]
        temp::Real = 288.15, [unit = "K"]
    end
    @outputs begin
        T::Real, [unit = "K"]
        p::Real, [unit = "Pa"]
        rho::Real, [unit = "kg/m^3"]
        a::Real, [unit = "m/s"]
        sigma::Real, [description = "Density ratio rho/rho0"]
    end
    @equations begin
        hc ~ clamp(h, h_min, h_max)
        T ~ ifelse(hc < h_trop, t0 - lapse * hc, t_trop)
        temp ~ T
        p ~ scale * ifelse(hc < h_trop,
                           p0 * (T / t0) ^ (g0 / (r_air * lapse)),
                           p_trop * exp(-g0 * (hc - h_trop) / (r_air * t_trop)))
        rho ~ p / (r_air * T)
        a ~ sqrt(gamma_air * r_air * T)
        sigma ~ rho / 1.225
    end
end
