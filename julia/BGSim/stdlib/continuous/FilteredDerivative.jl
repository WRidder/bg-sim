@block FilteredDerivative begin
    @inputs u::Real
    @outputs y::Real
    @parameters Tf::Real = 0.01, [unit = "s", min = 1.0e-9, description = "Filter time constant"]
    @variables x::Real = 0.0, [description = "Filter state"]
    @equations begin
        ddt(x) ~ (u - x) / Tf
        y ~ (u - x) / Tf
    end
end
