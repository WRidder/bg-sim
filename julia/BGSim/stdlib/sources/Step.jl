@block Step begin
    @outputs y::Real
    @parameters begin
        t_step::Real = 1.0, [unit = "s", min = 0, description = "Step time"]
        initial::Real = 0.0, [description = "Value before the step"]
        final::Real = 1.0, [description = "Value after the step"]
    end
    @equations y ~ ifelse(t >= t_step, final, initial)
end
