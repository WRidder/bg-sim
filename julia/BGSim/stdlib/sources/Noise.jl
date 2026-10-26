@block Noise begin
    @outputs y::Real
    @parameters begin
        mean::Real = 0.0, [description = "Mean of the noise"]
        std::Real = 1.0, [min = 0, description = "Standard deviation of the noise"]
        seed::Int = 1, [description = "Seed of the fixed pseudo-random sequence"]
        sample_time::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample time of the fixed clock"]
    end
    @variables begin
        k::Real = 0.0, [description = "Clock tick index"]
        u1::Real = 0.5, [description = "First uniform draw of the tick"]
        u2::Real = 0.5, [description = "Second uniform draw of the tick"]
    end
    @equations begin
        k ~ floor(t / sample_time)
        u1 ~ mod(sin(seed * 12.9898 + k * 78.233) * 43758.5453, 1.0) + 1.0e-12
        u2 ~ mod(sin(seed * 39.3468 + k * 11.135) * 24634.6345, 1.0)
        y ~ mean + std * sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
    end
end
