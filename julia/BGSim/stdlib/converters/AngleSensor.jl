@block AngleSensor begin
    @ports a::Power{Rotation}
    @outputs y::Real = 0.0, [unit = "rad"]
    @variables phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Sensed angle"]
    @equations begin
        a.e ~ 0.0
        ddt(phi) ~ a.f
        y ~ phi
    end
    @causality a => (:effort_out, :fixed)
end
