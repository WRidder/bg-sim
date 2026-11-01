@block SpeedHold begin
    # A test driver's right foot: a PI speed controller on the throttle (the validation runs
    # that need a constant speed: the skid pad, the grade climb). u = kp (v_ref - v) + xi,
    # xi' = ki (v_ref - v) - kaw (xi - clamp(xi, 0, 1)) (a smooth anti-windup that pulls the
    # integral back into 0..1, no switching events), throttle = clamp(u, 0, 1). No brake: the
    # runs only need to hold or gain speed.
    @inputs begin
        v::Real, [unit = "m/s", description = "Measured speed"]
        v_ref::Real, [unit = "m/s", description = "Target speed"]
    end
    @outputs y::Real, [unit = "1", description = "Throttle 0..1"]
    @parameters begin
        kp::Real = 0.5, [unit = "s/m", min = 0, description = "Proportional gain (throttle per m/s)"]
        ki::Real = 0.3, [unit = "1/m", min = 0, description = "Integral gain (throttle per m)"]
        kaw::Real = 20.0, [unit = "1/s", min = 0, description = "Anti-windup rate: pulls the integral back into 0..1"]
    end
    @variables begin
        xi::Real = 0.2, [unit = "1", state = :prefer, description = "Integral term"]
        e::Real = 0.0, [unit = "m/s", description = "Speed error"]
    end
    @equations begin
        e ~ v_ref - v
        ddt(xi) ~ ki * e - kaw * (xi - clamp(xi, 0.0, 1.0))
        y ~ clamp(kp * e + xi, 0.0, 1.0)
    end
end
