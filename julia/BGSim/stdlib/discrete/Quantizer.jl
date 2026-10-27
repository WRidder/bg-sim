@block Quantizer begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Input rounded to a multiple of the resolution"]
    @parameters resolution::Real = 1.0, [min = 1.0e-12, tunable = true, description = "Quantization step; half steps round away from zero"]
    @discrete Ts = sample_period begin
        y = resolution * round(u / resolution)
    end
end
