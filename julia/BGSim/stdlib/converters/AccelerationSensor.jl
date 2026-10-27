@block AccelerationSensor begin
    @ports a::Power{Translation}
    @outputs y::Real = 0.0, [unit = "m/s^2"]
    @variables v::Real = 0.0, [unit = "m/s", state = :prefer, description = "Sensed velocity whose derivative is the acceleration"]
    @equations begin
        a.e ~ 0.0
        v ~ a.f
        y ~ ddt(v)
    end
    @causality a => (:effort_out, :fixed)
end
