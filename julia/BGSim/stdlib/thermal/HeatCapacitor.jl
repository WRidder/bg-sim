@block HeatCapacitor begin
    @ports a::Power{Thermal}
    @parameters C::Real = 1000.0, [unit = "J/K", min = 1.0e-12, description = "Heat capacity: mass times specific heat, m*c_p"]
    @variables T::Real = 293.15, [unit = "K", state = :prefer, description = "Temperature; its start value is the initial temperature"]
    @equations begin
        # The thermal C element: the net heat flow into the body raises its temperature.
        ddt(T) ~ a.f / C
        a.e ~ T
    end
end
