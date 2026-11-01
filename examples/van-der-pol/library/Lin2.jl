@block Lin2 begin
    # Weighted sum of two signals plus a constant: y = k1 u1 + k2 u2 + c.
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @parameters begin
        k1::Real = 1.0, [description = "Weight of u1"]
        k2::Real = 1.0, [description = "Weight of u2"]
        c::Real = 0.0, [description = "Constant added"]
    end
    @equations y ~ k1 * u1 + k2 * u2 + c
end
