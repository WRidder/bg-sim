@block Mocap begin
    # 100 Hz motion-capture fix: world position and velocity, no bias, deterministic white
    # noise. It is the position/velocity source of the navigation filter (an indoor flight).
    # `n` counts the samples and doubles as the filter's fix-valid gate.
    @inputs begin
        p::Vec{3}
        v::Vec{3}
    end
    @outputs begin
        pm::Vec{3} = [0.0, 0.0, 0.0]
        vm::Vec{3} = [0.0, 0.0, 0.0]
        n::Real = 0.0
    end
    @parameters begin
        sigma_p::Real = 0.01, [unit = "m", min = 0, description = "Position noise per sample"]
        sigma_v::Real = 0.02, [unit = "m/s", min = 0, description = "Velocity noise per sample"]
        seed::Real = 11.0, [description = "Noise sequence selector"]
    end
    @variables k::Real = 0.0, [description = "Sample counter"]
    @discrete Ts = 10e-3 begin
        k = k + 1.0
        r = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for j in 1:6
            u1 = mod(sin(seed * 12.9898 + k * 78.233 + j * 37.719) * 43758.5453, 1.0) + 1.0e-12
            u2 = mod(sin(seed * 39.3468 + k * 11.135 + j * 93.989) * 24634.6345, 1.0)
            r[j] = sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
        end
        pm = p + sigma_p * [r[1], r[2], r[3]]
        vm = v + sigma_v * [r[4], r[5], r[6]]
        n = k
    end
end
