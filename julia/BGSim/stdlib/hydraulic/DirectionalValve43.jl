@block DirectionalValve43 begin
    # 4/3 proportional (servo) valve: supply P, return T, work ports A and B, and the
    # normalized spool position u from a signal (-1 to 1). Four metering edges, each with
    # the orifice's regularized law Q = Cd*A*sqrt(2/rho)*dp/(dp^2 + p_tr^2)^(1/4):
    #   u > 0 opens P->A and B->T, u < 0 opens P->B and A->T,
    #   area = A_leak + A_max*clamp((+-u - lap)/(1 - lap), 0, 1),
    # so every edge is fully open at |u| = 1 and stays at A_max beyond it. lap > 0 is an
    # overlap (a dead band of |u| < lap, closed centre), lap < 0 an underlap (open centre:
    # every edge passes A_max*(-lap)/(1 - lap) at u = 0), lap = 0 a critical centre. The
    # clamp is smooth (corners rounded over 1e-6 of the stroke), so there is no switching
    # event; A_leak keeps a closed edge well-posed.
    @ports begin
        P::Power{Hydraulic}
        T::Power{Hydraulic}
        A::Power{Hydraulic}
        B::Power{Hydraulic}
    end
    @inputs u::Real
    @parameters begin
        A_max::Real = 1.0e-5, [unit = "m^2", min = 0, description = "Area of each metering edge at full stroke"]
        A_leak::Real = 1.0e-9, [unit = "m^2", min = 0, description = "Leakage area of each closed edge"]
        lap::Real = 0.0, [unit = "1", min = -0.9, max = 0.9, description = "Spool lap as a fraction of the stroke: > 0 overlap (dead band), < 0 underlap (open centre)"]
        Cd::Real = 0.62, [unit = "1", min = 0, description = "Discharge coefficient"]
        rho::Real = 850.0, [unit = "kg/m^3", min = 1.0e-12, description = "Fluid density"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 0, description = "Transition pressure of the orifice regularization"]
    end
    @variables begin
        xp::Real = 0.0, [unit = "1", description = "Opening of P->A and B->T, 0 to 1"]
        xn::Real = 0.0, [unit = "1", description = "Opening of P->B and A->T, 0 to 1"]
        Q_PA::Real = 0.0, [unit = "m^3/s", description = "Flow from P to A"]
        Q_BT::Real = 0.0, [unit = "m^3/s", description = "Flow from B to T"]
        Q_PB::Real = 0.0, [unit = "m^3/s", description = "Flow from P to B"]
        Q_AT::Real = 0.0, [unit = "m^3/s", description = "Flow from A to T"]
    end
    @equations begin
        xp ~ 0.5 * (sqrt(((u - lap) / (1.0 - lap))^2 + 1.0e-12) -
                    sqrt(((u - lap) / (1.0 - lap) - 1.0)^2 + 1.0e-12) + 1.0)
        xn ~ 0.5 * (sqrt(((-u - lap) / (1.0 - lap))^2 + 1.0e-12) -
                    sqrt(((-u - lap) / (1.0 - lap) - 1.0)^2 + 1.0e-12) + 1.0)
        Q_PA ~ Cd * (A_leak + A_max * xp) * (P.e - A.e) *
               sqrt(2.0 / (rho * sqrt((P.e - A.e) * (P.e - A.e) + p_tr * p_tr)))
        Q_BT ~ Cd * (A_leak + A_max * xp) * (B.e - T.e) *
               sqrt(2.0 / (rho * sqrt((B.e - T.e) * (B.e - T.e) + p_tr * p_tr)))
        Q_PB ~ Cd * (A_leak + A_max * xn) * (P.e - B.e) *
               sqrt(2.0 / (rho * sqrt((P.e - B.e) * (P.e - B.e) + p_tr * p_tr)))
        Q_AT ~ Cd * (A_leak + A_max * xn) * (A.e - T.e) *
               sqrt(2.0 / (rho * sqrt((A.e - T.e) * (A.e - T.e) + p_tr * p_tr)))
        # Flow balance of the valve body: what enters at P leaves at A and B, and what
        # returns from A and B leaves at T.
        P.f ~ Q_PA + Q_PB
        T.f ~ -Q_BT - Q_AT
        A.f ~ Q_AT - Q_PA
        B.f ~ Q_BT - Q_PB
    end
end
