@block Polynomial begin
    # y = p[1]*u^(N-1) + p[2]*u^(N-2) + ... + p[N]: the polynomial with coefficients p, highest
    # power first (MATLAB's polyval), evaluated by Horner's rule h[1] = p[1],
    # h[i] = h[i-1]*u + p[i], y = h[N]. N is the number of coefficients, the degree plus one.
    @constants N::Int = 3, [min = 1, description = "Number of coefficients: the degree plus one"]
    @inputs u::Real
    @outputs y::Real
    @parameters p::Vec{N} = [1.0, 0.0, 0.0], [description = "Coefficients, highest power first"]
    @variables h::Vec{N}, [description = "Horner partial sums: h[i] is the polynomial of p[1..i]"]
    @equations begin
        h[1] ~ p[1]
        for i in 2:N
            h[i] ~ h[i - 1] * u + p[i]
        end
        y ~ h[N]
    end
end
