@block ElasticShaft begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real = 10.0, [unit = "N*m/rad", min = 0, description = "Torsional stiffness"]
        d::Real = 0.01, [unit = "N*m*s/rad", min = 0, description = "Torsional damping"]
    end
    @variables phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Twist angle a minus b"]
    @equations begin
        ddt(phi) ~ a.f - b.f
        a.e ~ k * phi + d * (a.f - b.f)
        b.e ~ -a.e
    end
end
