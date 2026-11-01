@block Cruise begin
    # Cruise control of the lorry: a drive force along the deck that holds the forward speed
    # (the body-frame twist component V[2]) at `v_set` with the time constant `tau`:
    #
    #     F = m / tau (v_set - V[2])
    #
    # The force goes to `DeckContact2D.Fd`, which shares it between the wheels in contact as a
    # traction along the panel, so the drive pushes through the tyres, not on the body. `v` is
    # the forward speed, recorded for the plots.
    @inputs V::Vec{3}
    @outputs begin
        F::Real, [unit = "N"]
        v::Real, [unit = "m/s"]
    end
    @parameters begin
        m::Real = 10000.0, [unit = "kg", min = 0, description = "Vehicle mass carried by this truss"]
        tau::Real = 0.5, [unit = "s", min = 1.0e-3, description = "Speed-control time constant"]
        v_set::Real = 10.0, [unit = "m/s", description = "Set speed"]
    end
    @equations begin
        F ~ m / tau * (v_set - V[2])
        v ~ V[2]
    end
end
