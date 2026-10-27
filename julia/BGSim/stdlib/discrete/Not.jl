@block Not begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Bool, [description = "Operand"]
    @outputs y::Bool = false, [description = "Logical negation of the input"]
    @discrete Ts = sample_period begin
        y = !u
    end
end
