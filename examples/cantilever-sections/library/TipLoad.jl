@block TipLoad begin
    # The tip force of the cantilevers, positive down, from t0 on (zero before):
    #   mode 0 "constant":        F0, applied as a step (t_ramp = 0) or a linear ramp over t_ramp;
    #   mode 1 "sine":            Fa sin(2 pi f (t - t0));
    #   mode 2 "constant + sine": both added, a sine about the constant load;
    #   mode 3 "sweep":           Fa sin(2 pi phase), a linear sweep from f_start to f_end over
    #                             T_sweep, then f_end (phase in cycles, as stdlib Chirp).
    @outputs F::Real, [unit = "N", description = "Tip force, positive down"]
    @parameters begin
        mode::Int = 0, [options = ["constant", "sine", "constant + sine", "sweep"], description = "Load: 0 constant (step or ramp), 1 sine, 2 constant + sine, 3 frequency sweep"]
        F0::Real = 250.0, [unit = "N", description = "Constant force"]
        t_ramp::Real = 0.0, [unit = "s", min = 0, description = "Ramp time of the constant force (0: a step)"]
        Fa::Real = 10.0, [unit = "N", description = "Sine amplitude"]
        f::Real = 6.4233, [unit = "Hz", min = 0, description = "Sine frequency"]
        f_start::Real = 2.0, [unit = "Hz", min = 0, description = "Start frequency of the sweep"]
        f_end::Real = 40.0, [unit = "Hz", min = 0, description = "End frequency of the sweep"]
        T_sweep::Real = 10.0, [unit = "s", min = 1.0e-9, description = "Duration of the sweep"]
        t0::Real = 0.2, [unit = "s", description = "Time at which the load starts"]
    end
    @variables begin
        tau::Real = 0.0, [unit = "s", description = "Time since t0 (0 before)"]
        ts::Real = 0.0, [unit = "s", description = "Time into the sweep, at most T_sweep"]
        Fc::Real = 0.0, [unit = "N", description = "Constant part"]
        Fs::Real = 0.0, [unit = "N", description = "Sine part"]
        Fw::Real = 0.0, [unit = "N", description = "Sweep"]
        cycles::Real = 0.0, [unit = "1", description = "Phase of the sweep in cycles"]
    end
    @equations begin
        tau ~ ifelse(t >= t0, t - t0, 0.0)
        ts ~ ifelse(tau <= T_sweep, tau, T_sweep)
        Fc ~ ifelse(t >= t0, F0 * ifelse(tau < t_ramp, tau / max(t_ramp, 1.0e-12), 1.0), 0.0)
        Fs ~ Fa * sin(6.283185307179586 * f * tau)
        cycles ~ f_start * ts + (f_end - f_start) * ts * ts / (2.0 * T_sweep) + f_end * (tau - ts)
        Fw ~ Fa * sin(6.283185307179586 * cycles)
        F ~ ifelse(mode == 0, Fc, ifelse(mode == 1, Fs, ifelse(mode == 2, Fc + Fs, Fw)))
    end
end
