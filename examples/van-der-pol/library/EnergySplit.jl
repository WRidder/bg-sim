@block EnergySplit begin
    # Integrates the power P absorbed by an element three ways: the net energy W = int P dt,
    # the energy it supplies W_sup = int max(-P, 0) dt and the energy it absorbs
    # W_abs = int max(P, 0) dt, so W = W_abs - W_sup.
    @inputs P::Real, [description = "Power absorbed by the element"]
    @outputs begin
        W::Real, [description = "Net energy absorbed"]
        W_sup::Real, [description = "Energy supplied (while P < 0)"]
        W_abs::Real, [description = "Energy absorbed (while P > 0)"]
    end
    @variables begin
        E::Real = 0.0, [state = :prefer, description = "Net energy"]
        Es::Real = 0.0, [state = :prefer, description = "Supplied energy"]
        Ea::Real = 0.0, [state = :prefer, description = "Absorbed energy"]
    end
    @equations begin
        ddt(E) ~ P
        ddt(Es) ~ max(-P, 0.0)
        ddt(Ea) ~ max(P, 0.0)
        W ~ E
        W_sup ~ Es
        W_abs ~ Ea
    end
end
