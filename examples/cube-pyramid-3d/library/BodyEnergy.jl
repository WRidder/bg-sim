@block BodyEnergy begin
    # Mechanical energy of one rigid body (X-MB5): a sensor, not plant physics.
    # `Ek = (1/2) P . V` from the momentum `P = [J w; m v]` and the twist `V = [w; v]` of the
    # `RigidBody3D` (both in the body frame), `Ep = m g0 z` from the world pose `g`.
    @inputs begin
        P::Vec{6}
        V::Vec{6}
        g::Vec{7}
    end
    @outputs begin
        Ek::Real, [unit = "J"]
        Ep::Real, [unit = "J"]
    end
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @equations begin
        Ek ~ 0.5 * (P[1] * V[1] + P[2] * V[2] + P[3] * V[3]) + 0.5 * (P[4] * V[4] + P[5] * V[5] + P[6] * V[6])
        Ep ~ m * g0 * g[7]
    end
end
