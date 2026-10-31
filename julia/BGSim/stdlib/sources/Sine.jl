@block Sine begin
    # Modelica.Blocks.Sources.Sine: from t_start on,
    # y = offset + amplitude*sin(frequency*(t - t_start) + phase); y = offset before t_start.
    # The frequency is angular (rad/s), as in MultiSine and ExpSine; Chirp uses Hz.
    #
    # With phase != 0 the output jumps at t_start, from offset to
    # offset + amplitude*sin(phase) (phase = pi/2 starts a cosine at its peak). The edge is an
    # exact event: the condition t >= t_start crosses zero through the two-term difference
    # t - t_start, which is exactly zero at the representable instant t_start, so an edge on
    # an output-grid time is landed once (no W206). With the default t_start = 0 the
    # condition never changes during a run that starts at 0, and the output is the plain
    # offset + amplitude*sin(frequency*t + phase).
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Amplitude"]
        frequency::Real = 1.0, [unit = "rad/s", description = "Angular frequency (rad/s; 2*pi*f for f in Hz)"]
        phase::Real = 0.0, [unit = "rad", description = "Phase at t_start; a non-zero phase makes the output jump at t_start"]
        offset::Real = 0.0, [description = "Offset; the output before t_start"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the sine starts; the output is offset before it"]
    end
    @equations begin
        y ~ offset + ifelse(
            t >= t_start,
            amplitude * sin(frequency * (t - t_start) + phase),
            0.0,
        )
    end
end
