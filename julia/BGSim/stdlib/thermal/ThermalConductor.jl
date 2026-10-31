@block ThermalConductor begin
    @ports begin
        a::Power{Thermal}
        b::Power{Thermal}
    end
    @parameters G::Real = 1.0, [unit = "W/K", min = 0, description = "Thermal conductance, k*A/L for a slab"]
    @variables begin
        dT::Real = 0.0, [unit = "K", description = "Temperature difference a minus b"]
        Q::Real = 0.0, [unit = "W", description = "Heat flow from a to b"]
    end
    @equations begin
        dT ~ a.e - b.e
        Q ~ G * dT
        a.f ~ Q
        b.f ~ -Q
    end
end
