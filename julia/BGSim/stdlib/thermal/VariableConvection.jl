@block VariableConvection begin
    @ports begin
        solid::Power{Thermal}
        fluid::Power{Thermal}
    end
    @inputs h::Real, [unit = "W/(m^2*K)"]
    @parameters A::Real = 0.01, [unit = "m^2", min = 0, description = "Wetted surface area"]
    @variables begin
        dT::Real = 0.0, [unit = "K", description = "Temperature difference solid minus fluid"]
        Q::Real = 0.0, [unit = "W", description = "Heat flow from the solid to the fluid"]
    end
    @equations begin
        # Newton's law of cooling with the heat transfer coefficient from a signal (a fan
        # speed map, a flow-dependent correlation).
        dT ~ solid.e - fluid.e
        Q ~ h * A * dT
        solid.f ~ Q
        fluid.f ~ -Q
    end
    @orientation begin
        solid => :in
        fluid => :in
    end
end
