@block GpsSensor begin
    # Slow position/velocity/heading sensor (RTK-GNSS or a motion-capture system plus a compass),
    # sampled at 50 Hz. Inputs are the TRUE world position `p`, world velocity `v` and yaw angle;
    # outputs are the sample held for 20 ms: truth plus white noise (no bias: an RTK fix has none
    # that matters at this scale). `n` counts the samples. The noise is the deterministic
    # sine-hash Box-Muller of `ImuSensor` (6 channels per sample).
    @inputs begin
        p::Vec{3}
        v::Vec{3}
        yaw::Real
    end
    @outputs begin
        pm::Vec{3} = [0.0, 0.0, 0.0]
        vm::Vec{3} = [0.0, 0.0, 0.0]
        psim::Real = 0.0
        n::Real = 0.0
    end
    @parameters begin
        sigma_p::Real = 0.02, [unit = "m", min = 0, description = "Position noise per sample"]
        sigma_v::Real = 0.05, [unit = "m/s", min = 0, description = "Velocity noise per sample"]
        sigma_psi::Real = 0.02, [unit = "rad", min = 0, description = "Heading noise per sample (about 1 deg)"]
        seed::Real = 7.0, [description = "Noise sequence selector"]
    end
    @variables k::Real = 0.0, [description = "Sample counter"]
    @discrete Ts = 20e-3 begin
        k = k + 1.0
        r = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for j in 1:7
            u1 = mod(sin(seed * 12.9898 + k * 78.233 + j * 37.719) * 43758.5453, 1.0) + 1.0e-12
            u2 = mod(sin(seed * 39.3468 + k * 11.135 + j * 93.989) * 24634.6345, 1.0)
            r[j] = sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
        end
        pm = p + sigma_p * [r[1], r[2], r[3]]
        vm = v + sigma_v * [r[4], r[5], r[6]]
        psim = yaw + sigma_psi * r[7]
        n = k
    end
end
