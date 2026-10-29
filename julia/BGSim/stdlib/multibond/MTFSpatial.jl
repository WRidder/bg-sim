@block MTFSpatial begin
    # Modulated spatial transformer: the diagonal `Vec{6}` modulus is a signal input, in the
    # same dimensionless form as `TFSpatial`'s parameter (a vector signal is unit-homogeneous
    # in v1, and a diagonal modulus is dimensionless, so one `unit = "1"` is exactly right).
    # `a.f[k] = u[k]*b.f[k]` and `b.e[k] = -u[k]*a.e[k]` keep
    # `a.e . a.f + b.e . b.f = 0` per component.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @inputs u::Vec{6}, [unit = "1", description = "Diagonal modulus signal per component"]
    @equations begin
        a.f[1] ~ u[1] * b.f[1]
        a.f[2] ~ u[2] * b.f[2]
        a.f[3] ~ u[3] * b.f[3]
        a.f[4] ~ u[4] * b.f[4]
        a.f[5] ~ u[5] * b.f[5]
        a.f[6] ~ u[6] * b.f[6]
        b.e[1] ~ -u[1] * a.e[1]
        b.e[2] ~ -u[2] * a.e[2]
        b.e[3] ~ -u[3] * a.e[3]
        b.e[4] ~ -u[4] * a.e[4]
        b.e[5] ~ -u[5] * a.e[5]
        b.e[6] ~ -u[6] * a.e[6]
    end
    @causality (a, b) => :transformer
end
