@block StoredEnergy begin
    # Energy of two quadratic stores, E = c1 (u1 - o1)^2 / 2 + c2 u2^2 / 2: a tank
    # (C v^2/2 + L i^2/2) or a mass on a spring (k (x - x_s)^2/2 + m v^2/2).
    @inputs begin
        u1::Real, [description = "First store's co-variable (capacitor voltage, block position)"]
        u2::Real, [description = "Second store's co-variable (inductor current, block velocity)"]
    end
    @outputs E::Real, [description = "Stored energy"]
    @parameters begin
        c1::Real = 1.0, [description = "First store's coefficient (C, k)"]
        c2::Real = 1.0, [description = "Second store's coefficient (L, m)"]
        o1::Real = 0.0, [description = "Offset of u1 (the block's position at the force balance)"]
    end
    @equations E ~ 0.5 * c1 * (u1 - o1) * (u1 - o1) + 0.5 * c2 * u2 * u2
end
