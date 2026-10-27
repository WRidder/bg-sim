@block PressureSensor begin
    @ports a::Power{Hydraulic}
    @outputs y::Real = 0.0, [unit = "Pa"]
    @equations begin
        a.f ~ 0.0
        y ~ a.e
    end
    @causality a => (:flow_out, :fixed)
end
