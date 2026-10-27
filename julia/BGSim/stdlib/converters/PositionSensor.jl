@block PositionSensor begin
    @ports a::Power{Translation}
    @outputs y::Real = 0.0, [unit = "m"]
    @variables x::Real = 0.0, [unit = "m", state = :prefer, description = "Sensed position"]
    @equations begin
        a.e ~ 0.0
        ddt(x) ~ a.f
        y ~ x
    end
    @causality a => (:effort_out, :fixed)
end
