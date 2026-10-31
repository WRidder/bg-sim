@block Sine begin
    # y = offset + amplitude*sin(frequency*(t - t_start) + phase) from t_start, y = offset
    # before it. The frequency is angular (rad/s); Chirp uses Hz.
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Amplitude"]
        frequency::Real = 1.0, [unit = "rad/s", description = "Angular frequency (rad/s; 2*pi*f for f in Hz)"]
        phase::Real = 0.0, [unit = "rad", description = "Phase at t_start"]
        offset::Real = 0.0, [description = "Offset; the output before t_start"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the sine starts; the output is offset before it"]
    end
    @equations y ~ offset + ifelse(t >= t_start, amplitude * sin(frequency * (t - t_start) + phase), 0.0)
end
