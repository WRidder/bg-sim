@block SpringDamper begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        k::Real = 1000.0, [unit = "N/m", min = 0, description = "Stiffness"]
        d::Real = 10.0, [unit = "N*s/m", min = 0, description = "Damping coefficient"]
    end
    @variables x::Real = 0.0, [unit = "m", state = :prefer, description = "Relative displacement"]
    @equations begin
        ddt(x) ~ a.f - b.f
        a.e ~ k * x + d * (a.f - b.f)
        b.e ~ -a.e
    end
end
