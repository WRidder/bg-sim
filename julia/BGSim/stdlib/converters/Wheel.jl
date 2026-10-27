@block Wheel begin
    @ports begin
        a::Power{Rotation}
        b::Power{Translation}
    end
    @parameters r::Real = 0.3, [unit = "m", min = 1.0e-9, description = "Wheel radius"]
    @equations begin
        # Rolling without slip against the ground represented by translation port b.
        b.f ~ r * a.f
        b.e ~ -a.e / r
    end
    @causality (a, b) => :transformer
end
