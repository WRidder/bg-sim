@block PrescribedTemperature begin
    @ports a::Power{Thermal}
    @inputs T::Real, [unit = "K"]
    @equations a.e ~ T
    @causality a => (:effort_out, :fixed)
end
