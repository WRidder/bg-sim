@block ResistorHeated begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        heat::Power{Thermal}
    end
    @parameters begin
        R0::Real = 1.0, [unit = "Ohm", min = 0, description = "Resistance at the reference temperature T0"]
        T0::Real = 293.15, [unit = "K", min = 0, description = "Reference temperature of R0"]
        alpha::Real = 0.0, [unit = "1/K", description = "Linear temperature coefficient (copper: 0.00393 1/K)"]
    end
    @variables begin
        R::Real = 1.0, [unit = "Ohm", description = "Resistance at the heat port temperature"]
        v::Real = 0.0, [unit = "V", description = "Voltage p minus n"]
        i::Real = 0.0, [unit = "A", description = "Current from p to n"]
        P::Real = 0.0, [unit = "W", description = "Dissipated electrical power, delivered as heat"]
    end
    @equations begin
        R ~ R0 * (1.0 + alpha * (heat.e - T0))
        v ~ p.e - n.e
        i ~ p.f
        p.f + n.f ~ 0.0
        v ~ R * i
        # Every joule dissipated leaves through the heat port (port flows count inward).
        P ~ v * i
        heat.f ~ -P
    end
    @orientation begin
        p => :in
        n => :in
        heat => :in
    end
end
