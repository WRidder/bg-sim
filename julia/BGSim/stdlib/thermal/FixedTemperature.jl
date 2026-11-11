@block FixedTemperature begin
    @ports a::Power{Thermal}
    @parameters T::Real = 293.15, [unit = "K", min = 0, description = "Fixed absolute temperature (293.15 K is 20 degC)"]
    @equations a.e ~ T
    @causality a => (:effort_out, :fixed)
    @orientation a => :in
end
