@block LossyGear begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        n::Real = 10.0, [unit = "1", min = 1.0e-12, description = "Gear ratio (a.f = n * b.f)"]
        eta::Real = 0.9, [unit = "1", min = 0, max = 1, description = "Efficiency when driven from a; the reciprocal applies when back-driven"]
    end
    @equations begin
        a.f ~ n * b.f
        # The efficiency follows the power direction: eta from a to b, the reciprocal when
        # the gear is back-driven from b.
        b.e ~ -n * a.e * ifelse(a.e * a.f > 0.0, eta, 1.0 / eta)
    end
    @causality (a, b) => :transformer
end
