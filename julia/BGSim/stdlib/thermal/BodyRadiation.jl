@block BodyRadiation begin
    @ports begin
        a::Power{Thermal}
        b::Power{Thermal}
    end
    @constants sigma::Real = 5.670374419e-8, [unit = "W/(m^2*K^4)", description = "Stefan-Boltzmann constant"]
    @parameters begin
        epsilon::Real = 0.9, [unit = "1", min = 0, max = 1, description = "Effective emissivity of the exchange"]
        A::Real = 0.01, [unit = "m^2", min = 0, description = "Radiating surface area"]
    end
    @variables Q::Real = 0.0, [unit = "W", description = "Net radiated heat flow from a to b"]
    @equations begin
        # Grey-body exchange between absolute temperatures: Q = epsilon*sigma*A*(Ta^4 - Tb^4).
        Q ~ epsilon * sigma * A * (a.e^4 - b.e^4)
        a.f ~ Q
        b.f ~ -Q
    end
end
