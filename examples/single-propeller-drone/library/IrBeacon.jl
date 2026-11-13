@block IrBeacon begin
    # 50 Hz IR-beacon absolute-yaw sensor. The vehicle has no magnetometer it can trust: the
    # motor current and the rotor dominate the magnetic field, so a ground beacon with a rotating
    # IR pattern gives the absolute heading (the ArduPilot fork's `AP_IRBeaconYaw`). The block
    # samples the true yaw with white noise and holds it; `n` counts the samples. A yaw rate
    # estimate is not provided: the gyro is much better at that.
    @inputs yaw::Real, [unit = "rad"]
    @outputs begin
        psim::Real = 0.0, [unit = "rad"]
        n::Real = 0.0
    end
    @parameters begin
        sigma_psi::Real = 0.01, [unit = "rad", min = 0, description = "Heading noise per sample (about 0.6 deg)"]
        seed::Real = 23.0, [description = "Noise sequence selector"]
    end
    @variables k::Real = 0.0, [description = "Sample counter"]
    @discrete Ts = 20e-3 begin
        k = k + 1.0
        u1 = mod(sin(seed * 12.9898 + k * 78.233 + 37.719) * 43758.5453, 1.0) + 1.0e-12
        u2 = mod(sin(seed * 39.3468 + k * 11.135 + 93.989) * 24634.6345, 1.0)
        r = sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
        psim = yaw + sigma_psi * r
        n = k
    end
end
