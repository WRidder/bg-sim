@block Exponentials begin
    # Modelica.Blocks.Sources.Exponentials: a first-order rise followed by a first-order
    # fall. From t_start, y = offset + amplitude*(1 - exp(-(t - t_start)/tau_rise)) for
    # rise_time; then the value reached decays with exp(-(t - t_start - rise_time)/tau_fall).
    # y = offset before t_start. A large rise_time gives a plain first-order step response.
    # Both switches are kinks (the output is continuous), located as exact time events.
    @outputs y::Real
    @parameters begin
        amplitude::Real = 1.0, [description = "Value the rise approaches above offset (Modelica outMax)"]
        rise_time::Real = 0.5, [unit = "s", min = 0, description = "Duration of the rise; the fall starts at t_start + rise_time"]
        tau_rise::Real = 0.1, [unit = "s", min = 1.0e-12, description = "Time constant of the rise"]
        tau_fall::Real = 0.1, [unit = "s", min = 1.0e-12, description = "Time constant of the fall"]
        offset::Real = 0.0, [description = "Offset; the output before t_start"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the rise starts"]
    end
    @equations begin
        y ~ offset + ifelse(
            t >= t_start + rise_time,
            amplitude * (1.0 - exp(-rise_time / tau_rise)) *
            exp(-(t - t_start - rise_time) / tau_fall),
            ifelse(t >= t_start, amplitude * (1.0 - exp(-(t - t_start) / tau_rise)), 0.0),
        )
    end
end
