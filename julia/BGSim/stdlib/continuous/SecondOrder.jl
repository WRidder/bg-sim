@block SecondOrder begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "Steady-state gain"]
        w0::Real = 1.0, [unit = "rad/s", min = 1.0e-9, description = "Undamped natural frequency"]
        zeta::Real = 0.7, [min = 0, description = "Damping ratio"]
    end
    @variables begin
        x1::Real = 0.0, [description = "Position state"]
        x2::Real = 0.0, [description = "Velocity state"]
    end
    @equations begin
        ddt(x1) ~ x2
        ddt(x2) ~ k * w0^2 * u - w0^2 * x1 - 2.0 * zeta * w0 * x2
        y ~ x1
    end
end
