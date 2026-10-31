@block Sine begin
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Amplitude"]
        frequency::Real = 1.0, [unit = "rad/s", description = "Angular frequency"]
        phase::Real = 0.0, [unit = "rad", description = "Phase"]
        offset::Real = 0.0, [description = "Offset"]
    end
    @equations y ~ offset + amplitude * sin(frequency * t + phase)
end
