@block ThermalResistor begin
    @ports begin
        a::Power{Thermal}
        b::Power{Thermal}
    end
    @parameters R::Real = 1.0, [unit = "K/W", min = 1.0e-12, description = "Thermal resistance, L/(k*A) for a slab"]
    @variables begin
        dT::Real = 0.0, [unit = "K", description = "Temperature difference a minus b"]
        Q::Real = 0.0, [unit = "W", description = "Heat flow from a to b"]
    end
    @equations begin
        dT ~ a.e - b.e
        dT ~ R * Q
        a.f ~ Q
        b.f ~ -Q
    end
    @orientation begin
        a => :in
        b => :in
    end
end
