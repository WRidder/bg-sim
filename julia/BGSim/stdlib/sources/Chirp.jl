@block Chirp begin
    # A frequency sweep from f_start to f_end over duration (frequencies in Hz, unlike Sine's
    # rad/s); afterwards the frequency stays at f_end. y = offset + amplitude*sin(2*pi*phase +
    # start_phase), where phase is the accumulated phase in cycles. The linear sweep raises
    # the frequency at a constant rate; the logarithmic sweep multiplies it by a constant
    # factor per second (f_start*(f_end/f_start)^(t/duration)), which needs f_start > 0,
    # f_end > 0 and f_start != f_end. The phase and the frequency are continuous at duration.
    @outputs y::Real
    @parameters begin
        f_start::Real = 1.0, [unit = "Hz", min = 0, description = "Start frequency of the sweep (Hz)"]
        f_end::Real = 10.0, [unit = "Hz", min = 0, description = "End frequency of the sweep (Hz)"]
        duration::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Duration of the sweep; afterwards the frequency stays at f_end"]
        amplitude::Real = 1.0, [description = "Amplitude"]
        offset::Real = 0.0, [description = "Offset"]
        start_phase::Real = 0.0, [unit = "rad", description = "Phase of the sine at t = 0"]
        method::Int = 0, [options = ["linear", "log"], description = "Sweep: 0 = linear in frequency, 1 = logarithmic (needs f_start > 0, f_end > 0 and f_start != f_end)"]
    end
    @variables phase::Real = 0.0, [unit = "1", description = "Accumulated phase in cycles"]
    @equations begin
        phase ~ ifelse(
            t <= duration,
            ifelse(
                method == 1,
                f_start * duration * (exp(log(f_end / f_start) * t / duration) - 1.0) /
                log(f_end / f_start),
                f_start * t + (f_end - f_start) * t * t / (2.0 * duration),
            ),
            ifelse(
                method == 1,
                (f_end - f_start) * duration / log(f_end / f_start) + f_end * (t - duration),
                f_start * duration + (f_end - f_start) * duration / 2.0 +
                f_end * (t - duration),
            ),
        )
        y ~ offset + amplitude * sin(6.283185307179586 * phase + start_phase)
    end
end
