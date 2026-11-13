@block FootSensor begin
    # The landing-gear load sensor: one load cell in each foot, read by the drive's ADC at its
    # own 400 Hz. Inputs are the TRUE normal forces of the four contacts; outputs are what the
    # drive and the mission get.
    #
    #   f      the four samples = truth + white noise (sigma per sample), held for one tick
    #   fn     their sum, the total landing-gear load
    #   touch  1 while fn > f_touch on this tick or on one of the last `n_hold - 1` ticks
    #   f_peak the largest fn sampled so far (a diagnostic, nothing reads it)
    #
    # A sample is up to one tick (2.5 ms) old when the drive acts on it, and a load that comes
    # and goes between two ticks is not seen at all. `touch` is stretched over `n_hold` ticks
    # (8 ticks = one 50 Hz period) so that the slower mission cannot miss a touch the drive saw.
    # The noise is deterministic, as in `ImuSensor` (Box-Muller on a sine hash, per tick and
    # channel); `seed` selects the sequence.
    @inputs leg::Vec{4}, [unit = "N", description = "True normal force of each foot"]
    @outputs begin
        f::Vec{4} = [0.0, 0.0, 0.0, 0.0], [unit = "N", description = "Sampled load of each foot"]
        fn::Real = 0.0, [unit = "N", description = "Sampled total landing-gear load"]
        touch::Real = 0.0, [description = "1 while the load is or just was above the threshold"]
        f_peak::Real = 0.0, [unit = "N", description = "Largest sampled total load so far"]
    end
    @parameters begin
        sigma::Real = 0.05, [unit = "N", min = 0, description = "White noise per sample and foot"]
        f_touch::Real = 2.0, [unit = "N", description = "Total load that counts as a touch"]
        n_hold::Real = 8.0, [min = 1, description = "Ticks the touch flag is held"]
        seed::Real = 2.0, [description = "Noise sequence selector"]
    end
    @variables begin
        k::Real = 0.0, [description = "Sample counter"]
        cnt::Real = 0.0, [description = "Ticks left of the touch hold"]
    end
    @discrete Ts = 2.5e-3 begin
        k = k + 1.0
        n = [0.0, 0.0, 0.0, 0.0]
        for j in 1:4
            u1 = mod(sin(seed * 12.9898 + k * 78.233 + j * 37.719) * 43758.5453, 1.0) + 1.0e-12
            u2 = mod(sin(seed * 39.3468 + k * 11.135 + j * 93.989) * 24634.6345, 1.0)
            n[j] = sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
        end
        fr = leg + sigma * n
        fs = fr[1] + fr[2] + fr[3] + fr[4]
        cnt = ifelse(fs > f_touch, n_hold, max(cnt - 1.0, 0.0))
        f = fr
        fn = fs
        touch = ifelse(cnt > 0.5, 1.0, 0.0)
        f_peak = max(f_peak, fs)
    end
end
