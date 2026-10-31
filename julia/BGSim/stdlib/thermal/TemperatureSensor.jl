@block TemperatureSensor begin
    @ports a::Power{Thermal}
    @outputs y::Real = 293.15, [unit = "K"]
    @equations begin
        a.f ~ 0.0
        y ~ a.e
    end
    @causality a => (:flow_out, :fixed)
end
