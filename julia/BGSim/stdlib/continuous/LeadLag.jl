@block LeadLag begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "Steady-state gain"]
        T_lead::Real = 0.1, [unit = "s", min = 0, description = "Zero (lead) time constant"]
        T_lag::Real = 1.0, [unit = "s", min = 1.0e-9, description = "Pole (lag) time constant"]
    end
    @variables x::Real = 0.0, [description = "Lag state"]
    @equations begin
        ddt(x) ~ (u - x) / T_lag
        y ~ k * ((1.0 - T_lead / T_lag) * x + (T_lead / T_lag) * u)
    end
end
