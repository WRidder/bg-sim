@block PressureSource begin
    @ports a::Power{Hydraulic}
    @inputs u::Real
    @parameters p::Real = 1.0e5, [unit = "Pa", description = "Pressure gain on the control input"]
    @equations a.e ~ p * u
    @causality a => (:effort_out, :fixed)
end
