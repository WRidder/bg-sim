@block PIController begin
    @parameters begin
        Kp::Real = 1.0, [tunable = true, description = "Proportional gain"]
        Ti::Real = 0.1, [unit = "s", min = 0, tunable = true, description = "Integral time"]
    end
    @inputs e::Real
    @outputs u::Real
    @variables x::Real = 0.0, [state = :prefer, description = "Integral state"]
    @equations begin
        ddt(x) ~ e / Ti
        u ~ Kp * (e + x)
    end
end
