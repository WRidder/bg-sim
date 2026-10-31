@block PWMAverage begin
    # The averaged model of PWM: the mean of the switched output over one carrier period,
    # low + (high - low)*clamp(u, 0, 1). It drops the carrier ripple and every switching
    # event, so a drive with a fast carrier simulates at the speed of its mechanics; swap
    # it for PWM (same parameters) to see the switching.
    @inputs u::Real, [description = "Duty cycle, 0..1 (clamped)"]
    @outputs y::Real, [description = "Average of the switched output over a carrier period"]
    @parameters begin
        high::Real = 1.0, [description = "Output of the switched PWM while on"]
        low::Real = 0.0, [description = "Output of the switched PWM while off"]
    end
    @equations begin
        y ~ low + (high - low) * clamp(u, 0.0, 1.0)
    end
end
