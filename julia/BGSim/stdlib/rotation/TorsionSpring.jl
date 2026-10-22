@block TorsionSpring begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real = 10.0, [unit = "N*m/rad", min = 0, description = "Torsional stiffness"]
        phi_free::Real = 0.0, [unit = "rad", description = "Free angle"]
    end
    @variables phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Relative angle"]
    @equations begin
        ddt(phi) ~ a.f - b.f
        a.e ~ k * (phi - phi_free)
        b.e ~ -a.e
    end
end
