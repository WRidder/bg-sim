@block Convection begin
    @ports begin
        solid::Power{Thermal}
        fluid::Power{Thermal}
    end
    @parameters begin
        h::Real = 10.0, [unit = "W/(m^2*K)", min = 0, description = "Convective heat transfer coefficient"]
        A::Real = 0.01, [unit = "m^2", min = 0, description = "Wetted surface area"]
    end
    @variables begin
        dT::Real = 0.0, [unit = "K", description = "Temperature difference solid minus fluid"]
        Q::Real = 0.0, [unit = "W", description = "Heat flow from the solid to the fluid"]
    end
    @equations begin
        # Newton's law of cooling with a constant film conductance h*A.
        dT ~ solid.e - fluid.e
        Q ~ h * A * dT
        solid.f ~ Q
        fluid.f ~ -Q
    end
end
