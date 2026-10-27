@block OneSidedSpring begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        kt::Real = 200000.0, [unit = "N/m", min = 0, description = "Contact stiffness"]
    end
    @variables x::Real = 0.0, [unit = "m", state = :prefer, description = "Compression from the free length (positive in contact)"]
    @outputs F::Real = 0.0, [unit = "N", description = "Contact force; zero when the tire has lifted off"]
    @equations begin
        # Copied from stdlib:translation/Spring and edited for the tire (plan 9.4): the
        # characteristic is one-sided, so the tire pushes but never pulls.
        ddt(x) ~ a.f - b.f
        F ~ ifelse(x > 0, kt * x, 0.0)
        a.e ~ F
        b.e ~ -F
    end
end
