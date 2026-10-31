@block BeltDrive begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        r_a::Real = 0.05, [unit = "m", min = 1.0e-9, description = "Radius of pulley a"]
        r_b::Real = 0.1, [unit = "m", min = 1.0e-9, description = "Radius of pulley b"]
        k::Real = 1.0e5, [unit = "N/m", min = 0, description = "Belt stiffness: tension difference per metre of stretch"]
        d::Real = 50.0, [unit = "N*s/m", min = 0, description = "Belt damping"]
    end
    @variables begin
        x::Real = 0.0, [unit = "m", state = :prefer, description = "Belt stretch: r_a*phi_a - r_b*phi_b"]
        F::Real = 0.0, [unit = "N", description = "Belt tension difference (tight side minus slack side)"]
    end
    @equations begin
        # Two pulleys joined by a compliant belt without slip: the stretch integrates the
        # difference of the belt speeds at the two pulleys, the tension difference is a
        # spring-damper on it, and each pulley feels the tension times its radius.
        ddt(x) ~ r_a * a.f - r_b * b.f
        F ~ k * x + d * (r_a * a.f - r_b * b.f)
        a.e ~ r_a * F
        b.e ~ -r_b * F
    end
end
