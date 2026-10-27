@block VelocitySource begin
    @ports a::Power{Translation}
    @inputs u::Real
    @parameters v::Real = 1.0, [unit = "m/s", description = "Velocity gain on the control input"]
    @equations a.f ~ v * u
    @causality a => (:flow_out, :fixed)
end
