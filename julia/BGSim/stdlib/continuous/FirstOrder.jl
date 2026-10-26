@block FirstOrder begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "Steady-state gain"]
        tau::Real = 1.0, [unit = "s", min = 1.0e-9, description = "Time constant"]
    end
    @variables x::Real = 0.0, [description = "Lag state"]
    @equations begin
        ddt(x) ~ (u - x) / tau
        y ~ k * x
    end
end
