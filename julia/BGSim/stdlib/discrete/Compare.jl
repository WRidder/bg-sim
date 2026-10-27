@block Compare begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs begin
        u1::Real, [description = "Left operand"]
        u2::Real, [description = "Right operand"]
    end
    @outputs y::Bool = false, [description = "Result of u1 op u2"]
    @parameters op::Int = 0, [options = ["==", "!=", "<", "<=", ">", ">="], description = "Comparison operator, selected by index"]
    @discrete Ts = sample_period begin
        if op == 0
            y = u1 == u2
        elseif op == 1
            y = u1 != u2
        elseif op == 2
            y = u1 < u2
        elseif op == 3
            y = u1 <= u2
        elseif op == 4
            y = u1 > u2
        else
            y = u1 >= u2
        end
    end
end
