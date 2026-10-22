@block SpeedSensor begin
    @ports a::Power{Rotation}
    @outputs y::Real = 0.0, [unit = "rad/s"]
    @equations begin
        a.e ~ 0.0
        y ~ a.f
    end
    @causality a => (:effort_out, :fixed)
end
