@block ALSysidCmd begin
    # Excitation set-points of the identification experiments, computed by the EtherCAT master at
    # the cycle rate (1 kHz) and sent to the drive (target torque for CST, target speed for CSV):
    #
    #   kind 1  torque step: tau = amp for t0 <= t < t0 + dur, else 0
    #   kind 2  speed staircase: w = levels[k] for the k-th window of length t_hold from t0
    #           (the windows alternate in sign through `levels`), 0 after the last one
    #   kind 3  torque triangle: amp * tri(2 pi (t - t0)/period) for n_per periods from t0
    #   kind 4  torque chirp: amp sin(2 pi (f0 tau + (f1 - f0) tau^2 / (2 dur))), tau = t - t0,
    #           for 0 <= tau < dur (a linear sweep from f0 to f1)
    @constants NL::Int = 12
    @inputs tm::Real, [unit = "s"]
    @outputs begin
        tau_cmd::Real = 0.0, [unit = "N*m", description = "Target torque"]
        w_cmd::Real = 0.0, [unit = "rad/s", description = "Target speed"]
    end
    @parameters begin
        kind::Real = 1.0, [description = "1 step, 2 staircase, 3 triangle, 4 chirp"]
        t0::Real = 0.01, [unit = "s", description = "Start"]
        amp::Real = 1.0, [description = "Amplitude (N m)"]
        dur::Real = 0.05, [unit = "s", description = "Duration (step, chirp)"]
        t_hold::Real = 1.0, [unit = "s", description = "Window of one staircase level"]
        levels::Vec{NL} = [0.2, -0.2, 0.5, -0.5, 1.0, -1.0, 2.0, -2.0, 4.0, -4.0, 8.0, -8.0], [unit = "rad/s", description = "Staircase speeds"]
        period::Real = 4.0, [unit = "s", description = "Triangle period"]
        n_per::Real = 2.0, [description = "Triangle periods"]
        f0::Real = 0.2, [unit = "Hz", description = "Chirp start frequency"]
        f1::Real = 5.0, [unit = "Hz", description = "Chirp end frequency"]
    end
    @discrete Ts = 1e-3 begin
        tau = tm - t0
        u = 0.0
        w = 0.0
        if kind < 1.5
            if tau >= 0.0 && tau < dur
                u = amp
            end
        elseif kind < 2.5
            if tau >= 0.0
                k = floor(tau / t_hold)
                for i in 1:NL
                    if abs(k - (i - 1)) < 0.5
                        w = levels[i]
                    end
                end
            end
        elseif kind < 3.5
            if tau >= 0.0 && tau < n_per * period
                s = tau / period - floor(tau / period)
                u = amp * ifelse(s < 0.25, 4.0 * s, ifelse(s < 0.75, 2.0 - 4.0 * s, 4.0 * s - 4.0))
            end
        else
            if tau >= 0.0 && tau < dur
                u = amp * sin(6.283185307179586 * (f0 * tau + (f1 - f0) * tau * tau / (2.0 * dur)))
            end
        end
        tau_cmd = u
        w_cmd = w
    end
end
