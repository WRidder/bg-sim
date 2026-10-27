@block RackAndPinion begin
    @ports begin
        a::Power{Rotation}
        b::Power{Translation}
    end
    @parameters r::Real = 0.02, [unit = "m", min = 1.0e-9, description = "Pinion radius"]
    @equations begin
        # Rolling without slip: the rack speed is r times the pinion speed, and the force is
        # the torque divided by r with the opposite sign (power positive into each port).
        b.f ~ r * a.f
        b.e ~ -a.e / r
    end
    @causality (a, b) => :transformer
end
