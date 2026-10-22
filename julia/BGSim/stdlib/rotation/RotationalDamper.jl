@block RotationalDamper begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters d::Real = 1e-3, [unit = "N*m*s/rad", min = 0, description = "Damping coefficient"]
    @equations begin
        a.e ~ d * (a.f - b.f)
        b.e ~ -a.e
    end
end
