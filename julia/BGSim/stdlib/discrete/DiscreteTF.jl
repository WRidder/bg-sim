@block DiscreteTF begin
    @constants N::Int = 3
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Filtered output"]
    @parameters begin
        b::Vec{N} = [0.5, 0.25, 0.0], [description = "Numerator coefficients in z: b[1] + b[2]*z^-1 + ..."]
        a::Vec{N} = [1.0, -0.5, 0.0], [description = "Denominator coefficients in z: a[1] + a[2]*z^-1 + ..."]
    end
    @variables begin
        uh::Vec{N} = [0.0, 0.0, 0.0], [description = "Input history, uh[k] is u from k ticks ago"]
        yh::Vec{N} = [0.0, 0.0, 0.0], [description = "Output history, yh[k] is y from k ticks ago"]
    end
    @discrete Ts = sample_period begin
        acc = b[1] * u
        for k in 2:N
            acc = acc + b[k] * uh[k - 1]
        end
        for k in 2:N
            acc = acc - a[k] * yh[k - 1]
        end
        y = acc / a[1]
        hu = uh
        hy = yh
        for k in 2:N
            hu[k] = uh[k - 1]
            hy[k] = yh[k - 1]
        end
        hu[1] = u
        hy[1] = y
        uh = hu
        yh = hy
    end
end
