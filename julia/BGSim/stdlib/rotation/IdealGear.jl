@block IdealGear begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters n::Real = 1.0, [min = 0, description = "Gear ratio (a.f = n * b.f)"]
    @equations begin
        a.f ~ n * b.f
        b.e ~ -n * a.e
    end
    @causality (a, b) => :transformer
end
