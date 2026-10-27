@block Orifice begin
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @parameters begin
        Cd::Real = 0.62, [unit = "1", min = 0, description = "Discharge coefficient"]
        A::Real = 1.0e-6, [unit = "m^2", min = 0, description = "Orifice area"]
        rho::Real = 850.0, [unit = "kg/m^3", min = 1.0e-12, description = "Fluid density"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 0, description = "Transition pressure of the regularization"]
    end
    @variables begin
        dp::Real = 0.0, [unit = "Pa", description = "Pressure drop a minus b"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Flow from a to b"]
    end
    @equations begin
        dp ~ a.e - b.e
        # The plan's regularized law, Q = Cd*A*sqrt(2/rho) * dp/(dp^2 + p_tr^2)^(1/4).
        # Squaring the branch keeps the sign of dp and needs only integer exponents, which
        # is what the unit checker accepts for a dimensioned base.
        Q ~ ifelse(
            dp > 0.0,
            sqrt(Cd * Cd * A * A * 2.0 * dp * dp / (rho * sqrt(dp * dp + p_tr * p_tr))),
            ifelse(
                dp < 0.0,
                -sqrt(Cd * Cd * A * A * 2.0 * dp * dp / (rho * sqrt(dp * dp + p_tr * p_tr))),
                0.0,
            ),
        )
        a.f ~ Q
        b.f ~ -Q
    end
end
