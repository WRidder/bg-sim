@block RateLimitedLag begin
    # An actuator: a first-order lag with a rate limit (signal only),
    #
    #   dy/dt = clamp((u - y) / tau, -rate, rate)
    #
    # The wind turbine uses it twice: as the blade-pitch actuator (tau 50 ms, 8 deg/s, the
    # report's pitch-rate limit) and as the power converter's torque loop (tau 50 ms,
    # 15 kN m/s, the report's generator-torque rate limit). The stdlib RateLimiter has a fixed
    # 1 s time constant inside its rate band, too slow for either.
    @inputs u::Real, [description = "Command"]
    @outputs y::Real, [description = "Actuator output"]
    @parameters begin
        tau::Real = 0.05, [unit = "s", min = 1.0e-6, description = "Time constant inside the rate band"]
        rate::Real = 1.0, [min = 0, description = "Rate limit (units of u per second)"]
    end
    @variables x::Real = 0.0, [state = :prefer, description = "Actuator state"]
    @equations begin
        ddt(x) ~ clamp((u - x) / tau, -rate, rate)
        y ~ x
    end
end
