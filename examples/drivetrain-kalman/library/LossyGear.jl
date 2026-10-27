@block LossyGear begin
    @ports begin
        a::Power{Rotation}    # input shaft (fast)
        b::Power{Rotation}    # output shaft (slow)
    end
    @parameters begin
        n::Real   = 10.0                    # a.f = n * b.f
        eta::Real = 0.9, [min = 0, max = 1] # efficiency
    end
    @equations begin
        a.f ~ n * b.f
        # efficiency depends on power direction: driven from a, or back-driven from b
        b.e ~ -n * a.e * ifelse(a.e * a.f > 0, eta, 1/eta)
    end
end
