@block MutualInductance begin
    @ports begin
        p1::Power{Electrical}
        n1::Power{Electrical}
        p2::Power{Electrical}
        n2::Power{Electrical}
    end
    @parameters begin
        L1::Real = 1.0e-3, [unit = "H", min = 1.0e-15, description = "Self-inductance of winding 1 (p1-n1)"]
        L2::Real = 1.0e-3, [unit = "H", min = 1.0e-15, description = "Self-inductance of winding 2 (p2-n2)"]
        k::Real = 0.9, [unit = "1", min = 0, max = 0.999999, description = "Coupling coefficient, below 1; the mutual inductance is M = k*sqrt(L1*L2), both windings dotted at p"]
    end
    @variables begin
        i1::Real = 0.0, [unit = "A", state = :prefer, description = "Current through winding 1, from p1 to n1"]
        i2::Real = 0.0, [unit = "A", state = :prefer, description = "Current through winding 2, from p2 to n2"]
    end
    @equations begin
        p1.f + n1.f ~ 0.0
        p2.f + n2.f ~ 0.0
        p1.f ~ i1
        p2.f ~ i2
        # The two-port I-field v = L * di/dt with L = [L1 M; M L2], inverted (its
        # determinant L1*L2*(1 - k^2) is positive for k < 1). The stored energy is
        # L1*i1^2/2 + M*i1*i2 + L2*i2^2/2.
        ddt(i1) ~ (L2 * (p1.e - n1.e) - k * sqrt(L1 * L2) * (p2.e - n2.e)) / (L1 * L2 * (1.0 - k^2))
        ddt(i2) ~ (L1 * (p2.e - n2.e) - k * sqrt(L1 * L2) * (p1.e - n1.e)) / (L1 * L2 * (1.0 - k^2))
    end
    @orientation begin
        p1 => :in
        n1 => :in
        p2 => :in
        n2 => :in
    end
end
