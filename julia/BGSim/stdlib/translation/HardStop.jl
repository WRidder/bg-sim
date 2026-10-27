@block HardStop begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        lower::Real = -0.01, [unit = "m", description = "Lower limit of the free travel"]
        upper::Real = 0.01, [unit = "m", description = "Upper limit of the free travel"]
        k::Real = 1.0e5, [unit = "N/m", min = 0, description = "Contact stiffness"]
        d::Real = 100.0, [unit = "N*s/m", min = 0, description = "Contact damping coefficient"]
    end
    @variables x::Real = 0.0, [unit = "m", state = :prefer, description = "Relative displacement"]
    @equations begin
        ddt(x) ~ a.f - b.f
        # Dead-zone contact: no force between the limits, a spring-damper outside them. The
        # two `ifelse` conditions are the switching instants the event collector lands on.
        a.e ~ ifelse(
            x > upper,
            k * (x - upper) + d * (a.f - b.f),
            ifelse(x < lower, k * (x - lower) + d * (a.f - b.f), 0.0),
        )
        b.e ~ -a.e
    end
end
