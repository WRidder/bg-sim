@block ExpSine begin
    # A damped sine (Modelica.Blocks.Sources.ExpSine): from t_start on,
    # y = offset + amplitude*exp(-damping*(t - t_start))*sin(frequency*(t - t_start) + phase);
    # y = offset before t_start. The frequency is angular (rad/s), as in Sine.
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Amplitude at t_start, before the decay"]
        frequency::Real = 10.0, [unit = "rad/s", description = "Angular frequency (rad/s, as in Sine; 2*pi*f for f in Hz)"]
        phase::Real = 0.0, [unit = "rad", description = "Phase at t_start"]
        damping::Real = 1.0, [unit = "1/s", min = 0, description = "Decay rate of the envelope exp(-damping*(t - t_start))"]
        offset::Real = 0.0, [description = "Offset; the output before t_start"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the damped sine starts"]
    end
    @equations begin
        y ~ offset + ifelse(
            t >= t_start,
            amplitude * exp(-damping * (t - t_start)) * sin(frequency * (t - t_start) + phase),
            0.0,
        )
    end
end
