@block Saturation begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        lower::Real = -1.0, [tunable = true, description = "Lower output limit"]
        upper::Real = 1.0, [tunable = true, description = "Upper output limit"]
    end
    @equations y ~ clamp(u, lower, upper)
end
