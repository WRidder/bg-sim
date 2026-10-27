@block VelocitySensor begin
    @ports a::Power{Translation}
    @outputs y::Real = 0.0, [unit = "m/s"]
    @equations begin
        a.e ~ 0.0
        y ~ a.f
    end
    @causality a => (:effort_out, :fixed)
end
