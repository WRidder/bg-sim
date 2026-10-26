@block RateLimiter begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        rising::Real = 1.0, [min = 0, tunable = true, description = "Maximum rising rate per second"]
        falling::Real = 1.0, [min = 0, tunable = true, description = "Maximum falling rate per second"]
    end
    @variables s::Real = 0.0, [description = "Limited output state"]
    @equations begin
        ddt(s) ~ clamp(u - s, -falling, rising)
        y ~ s
    end
end
