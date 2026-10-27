@block IIR begin
    @constants N::Int = 3
    @constants M::Int = 2
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Filtered output"]
    @parameters begin
        b::Vec{N} = [0.5, 0.5, 0.0], [description = "Feedforward coefficients: b[1] is the newest sample"]
        a::Vec{M} = [1.0, -0.5], [description = "Feedback coefficients: a[1] is the output gain, a[k] multiplies y from k-1 ticks ago"]
    end
    @variables begin
        uh::Vec{N} = [0.0, 0.0, 0.0], [description = "Input history, uh[k] is the sample from k-1 ticks ago"]
        yh::Vec{M} = [0.0, 0.0], [description = "Output history, yh[k] is the output from k-1 ticks ago"]
    end
    @discrete Ts = sample_period begin
        acc = b[1] * u
        for k in 2:N
            acc = acc + b[k] * uh[k - 1]
        end
        for k in 2:M
            acc = acc - a[k] * yh[k - 1]
        end
        y = acc / a[1]
        hu = uh
        hy = yh
        for k in 2:N
            hu[k] = uh[k - 1]
        end
        for k in 2:M
            hy[k] = yh[k - 1]
        end
        hu[1] = u
        hy[1] = y
        uh = hu
        yh = hy
    end
end
