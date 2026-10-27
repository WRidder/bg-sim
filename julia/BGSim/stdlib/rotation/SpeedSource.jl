@block SpeedSource begin
    @ports a::Power{Rotation}
    @inputs u::Real
    @parameters w::Real = 1.0, [unit = "rad/s", description = "Angular speed gain on the control input"]
    @equations a.f ~ w * u
    @causality a => (:flow_out, :fixed)
end
