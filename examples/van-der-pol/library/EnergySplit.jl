@block EnergySplit begin
    # Integrates the power P absorbed by an element three ways: the net energy W = int P dt,
    # the energy it supplies W_sup = int max(-P, 0) dt and the energy it absorbs
    # W_abs = int max(P, 0) dt, so W = W_abs - W_sup.
    #
    # The two halves are written as (s -+ P)/2 with s = sqrt(P^2 + P_eps^2), not with max():
    # max(P, 0) adds a zero-crossing callback on P, and the powers here (the contact of the belt,
    # the tunnel diode) touch zero without changing sign (P ~ -x'^2 near x' = 0). Rounding then
    # flips the sign of P on such a touch again and again, and the root finder never gets past
    # it (the solver stops with MaxIters). The smooth form has no callback; W_abs - W_sup = P
    # still holds exactly, both stay >= 0, and the error is a bias of P_eps/2 per second.
    @inputs P::Real, [description = "Power absorbed by the element"]
    @outputs begin
        W::Real, [description = "Net energy absorbed"]
        W_sup::Real, [description = "Energy supplied (while P < 0)"]
        W_abs::Real, [description = "Energy absorbed (while P > 0)"]
    end
    @parameters begin
        P_eps::Real = 1.0e-12, [min = 0, description = "Smoothing power of |P| (far below the power scale)"]
    end
    @variables begin
        E::Real = 0.0, [state = :prefer, description = "Net energy"]
        Es::Real = 0.0, [state = :prefer, description = "Supplied energy"]
        Ea::Real = 0.0, [state = :prefer, description = "Absorbed energy"]
        s::Real = 0.0, [description = "Smooth |P|"]
    end
    @equations begin
        s ~ sqrt(P * P + P_eps * P_eps)
        ddt(E) ~ P
        ddt(Es) ~ 0.5 * (s - P)
        ddt(Ea) ~ 0.5 * (s + P)
        W ~ E
        W_sup ~ Es
        W_abs ~ Ea
    end
end
