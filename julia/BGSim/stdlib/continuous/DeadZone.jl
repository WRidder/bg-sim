@block DeadZone begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        lower::Real = -0.5, [tunable = true, description = "Lower edge of the dead zone"]
        upper::Real = 0.5, [tunable = true, description = "Upper edge of the dead zone"]
    end
    @equations y ~ deadzone(u, lower, upper)
end
