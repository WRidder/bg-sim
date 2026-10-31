@block PressureReliefValve begin
    # Direct-acting pressure relief valve from the protected line a to the tank side b. It
    # is closed (leakage only) while dp = a.e - b.e stays below the set pressure, opens over
    # the regulation range dp_reg and is fully open at p_set + dp_reg; the opening is a
    # smooth clamp (corners rounded over 0.1% of dp_reg, no switching event). With a flow Q
    # into the line the pressure settles where the valve passes Q, between p_set and
    # p_set + dp_reg as long as Q stays below the full-open flow. The flow is the orifice's
    # regularized law, smooth through dp = 0.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @parameters begin
        p_set::Real = 1.0e7, [unit = "Pa", description = "Set (cracking) pressure"]
        dp_reg::Real = 5.0e5, [unit = "Pa", min = 1.0e-12, description = "Regulation range: the valve is fully open at p_set + dp_reg"]
        A_max::Real = 5.0e-5, [unit = "m^2", min = 0, description = "Flow area when fully open"]
        A_leak::Real = 1.0e-11, [unit = "m^2", min = 0, description = "Leakage area of the closed valve"]
        Cd::Real = 0.62, [unit = "1", min = 0, description = "Discharge coefficient"]
        rho::Real = 850.0, [unit = "kg/m^3", min = 1.0e-12, description = "Fluid density"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 0, description = "Transition pressure of the orifice regularization"]
    end
    @variables begin
        dp::Real = 0.0, [unit = "Pa", description = "Pressure drop a minus b"]
        x::Real = 0.0, [unit = "1", description = "Opening, 0 closed to 1 fully open"]
        A::Real = 0.0, [unit = "m^2", description = "Flow area"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Relief flow from a to b"]
    end
    @equations begin
        dp ~ a.e - b.e
        # Smooth clamp of (dp - p_set)/dp_reg to [0, 1], as in CheckValve.
        x ~ 0.5 * (sqrt(((dp - p_set) / dp_reg)^2 + 1.0e-6) -
                   sqrt(((dp - p_set) / dp_reg - 1.0)^2 + 1.0e-6) + 1.0)
        A ~ A_leak + (A_max - A_leak) * x
        Q ~ Cd * A * dp * sqrt(2.0 / (rho * sqrt(dp * dp + p_tr * p_tr)))
        a.f ~ Q
        b.f ~ -Q
    end
end
