@block FIR begin
    @constants N::Int = 3
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Filtered output, the weighted sum of the last N samples"]
    @parameters b::Vec{N} = [0.25, 0.5, 0.25], [description = "Feedforward coefficients: b[1] is the newest sample"]
    @variables uh::Vec{N} = [0.0, 0.0, 0.0], [description = "Input history, uh[k] is the sample from k-1 ticks ago"]
    @discrete Ts = sample_period begin
        acc = b[1] * u
        for k in 2:N
            acc = acc + b[k] * uh[k - 1]
        end
        y = acc
        hu = uh
        for k in 2:N
            hu[k] = uh[k - 1]
        end
        hu[1] = u
        uh = hu
    end
end
