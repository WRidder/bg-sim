@block Spring begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        k::Real = 1000.0, [unit = "N/m", min = 0, description = "Stiffness"]
        x_free::Real = 0.0, [unit = "m", description = "Free length"]
    end
    @variables x::Real = 0.0, [unit = "m", state = :prefer, description = "Relative displacement"]
    @equations begin
        ddt(x) ~ a.f - b.f
        a.e ~ k * (x - x_free)
        b.e ~ -a.e
    end
end
