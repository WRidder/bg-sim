@block Chirp begin
    @outputs y::Real
    @parameters begin
        f_start::Real = 1.0, [unit = "Hz", min = 0, description = "Start frequency of the sweep"]
        f_end::Real = 10.0, [unit = "Hz", min = 0, description = "End frequency of the sweep"]
        duration::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Duration of the sweep; afterwards the frequency stays at f_end"]
    end
    @variables phase::Real = 0.0, [unit = "1", description = "Accumulated phase in cycles"]
    @equations begin
        phase ~ ifelse(
            t <= duration,
            f_start * t + (f_end - f_start) * t * t / (2.0 * duration),
            f_start * duration + (f_end - f_start) * duration / 2.0 +
            f_end * (t - duration),
        )
        y ~ sin(6.283185307179586 * phase)
    end
end
