@block MTFPlanar begin
    # Modulated planar transformer: `stdlib:multibond/MTFPlanar` is the planar `MTF` of the
    # plan's element list (the `Planar` suffix avoids a catalog-name collision with the
    # scalar `stdlib:bondgraph/MTF`).
    #
    # The modulus is the signal input `u`, a diagonal `Vec{3}` in the same dimensionless form
    # as `TFPlanar`'s parameter (a vector signal is unit-homogeneous in v1, and a diagonal
    # modulus is dimensionless, so one `unit = "1"` is exactly right here). `a.f[k] =
    # u[k]*b.f[k]` and `b.e[k] = -u[k]*a.e[k]` keep `a.e . a.f + b.e . b.f = 0`; a full matrix
    # modulation would need the inverse transpose and is not offered (see `TFPlanar`).
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @inputs u::Vec{3}, [unit = "1"]
    @equations begin
        a.f[1] ~ u[1] * b.f[1]
        a.f[2] ~ u[2] * b.f[2]
        a.f[3] ~ u[3] * b.f[3]
        b.e[1] ~ -u[1] * a.e[1]
        b.e[2] ~ -u[2] * a.e[2]
        b.e[3] ~ -u[3] * a.e[3]
    end
    @causality (a, b) => :transformer
end
