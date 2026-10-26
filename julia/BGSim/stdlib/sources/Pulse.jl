@block Pulse begin
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Pulse amplitude"]
        period::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Pulse period"]
        duty::Real = 0.5, [min = 0, max = 1, description = "Duty cycle: the high fraction of each period"]
        t_start::Real = 0.0, [unit = "s", description = "Time of the first rising edge"]
    end
    @equations begin
        y ~ ifelse(
            t >= t_start && sin(
                6.283185307179586 * (t - t_start) / period + 1.5707963267948966 -
                3.141592653589793 * duty,
            ) > cos(3.141592653589793 * duty),
            amplitude,
            0.0,
        )
    end
end
