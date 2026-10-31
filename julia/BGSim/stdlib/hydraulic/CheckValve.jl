@block CheckValve begin
    # Check valve: flow from a to b once the pressure drop dp = a.e - b.e exceeds the
    # cracking pressure. The opening grows from zero at p_crack to full at p_crack + dp_open
    # (a smooth clamp, corners rounded over 0.1% of dp_open, so there is no switching event),
    # and the leakage area A_leak keeps the closed valve well-posed. The flow is the
    # orifice's regularized law, Q = Cd*A*sqrt(2/rho)*dp/(dp^2 + p_tr^2)^(1/4), written as
    # Cd*A*dp*sqrt(2/(rho*sqrt(dp^2 + p_tr^2))) so it is smooth through dp = 0 without a
    # branch. Reverse flow only passes the leakage.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @parameters begin
        p_crack::Real = 1.0e5, [unit = "Pa", description = "Cracking pressure: the valve starts to open above it"]
        dp_open::Real = 2.0e5, [unit = "Pa", min = 1.0e-12, description = "Pressure rise above p_crack at which the valve is fully open"]
        A_max::Real = 1.0e-5, [unit = "m^2", min = 0, description = "Flow area when fully open"]
        A_leak::Real = 1.0e-11, [unit = "m^2", min = 0, description = "Leakage area of the closed valve"]
        Cd::Real = 0.62, [unit = "1", min = 0, description = "Discharge coefficient"]
        rho::Real = 850.0, [unit = "kg/m^3", min = 1.0e-12, description = "Fluid density"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 0, description = "Transition pressure of the orifice regularization"]
    end
    @variables begin
        dp::Real = 0.0, [unit = "Pa", description = "Pressure drop a minus b"]
        x::Real = 0.0, [unit = "1", description = "Opening, 0 closed to 1 fully open"]
        A::Real = 0.0, [unit = "m^2", description = "Flow area"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Flow from a to b"]
    end
    @equations begin
        dp ~ a.e - b.e
        # Smooth clamp of (dp - p_crack)/dp_open to [0, 1]: (|s| - |s - 1| + 1)/2 with the
        # absolute values rounded as sqrt(s^2 + 1e-6).
        x ~ 0.5 * (sqrt(((dp - p_crack) / dp_open)^2 + 1.0e-6) -
                   sqrt(((dp - p_crack) / dp_open - 1.0)^2 + 1.0e-6) + 1.0)
        A ~ A_leak + (A_max - A_leak) * x
        Q ~ Cd * A * dp * sqrt(2.0 / (rho * sqrt(dp * dp + p_tr * p_tr)))
        a.f ~ Q
        b.f ~ -Q
    end
end
