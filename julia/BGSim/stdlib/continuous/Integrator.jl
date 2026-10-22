@block Integrator begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        lower::Real = -1e30, [description = "Lower saturation limit (1e30 means none)"]
        upper::Real = 1e30, [description = "Upper saturation limit (1e30 means none)"]
    end
    @variables x::Real = 0.0, [state = :prefer, description = "Integrator state"]
    @equations begin
        ddt(x) ~ u
        y ~ clamp(x, lower, upper)
    end
end
