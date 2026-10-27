@block And begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs begin
        u1::Bool, [description = "First operand"]
        u2::Bool, [description = "Second operand"]
    end
    @outputs y::Bool = false, [description = "u1 and u2; chain instances for more inputs"]
    @discrete Ts = sample_period begin
        y = ifelse(u1, u2, false)
    end
end
