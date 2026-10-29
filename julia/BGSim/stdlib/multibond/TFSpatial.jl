@block TFSpatial begin
    # Spatial **diagonal** transformer (the spatial `TF`): a dimensionless `Vec{6}` modulus,
    #
    #     a.f[k] = n[k] b.f[k],     b.e[k] = -n[k] a.e[k],
    #
    # written component-wise. Power continuity is per component:
    # `a.e[k]*a.f[k] + b.e[k]*b.f[k] = (n[k] - n[k]) a.e[k] b.f[k] = 0`. The diagonal form is
    # kept because its modulus is unit-homogeneous (dimensionless), so the scalar unit checker
    # still sees every port component's own unit (D-MB10). The general 6x6 form is
    # `TFSpatialMat`.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @parameters begin
        n::Vec{6} = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0], [unit = "1", description = "Diagonal transformer modulus per component"]
    end
    @equations begin
        a.f[1] ~ n[1] * b.f[1]
        a.f[2] ~ n[2] * b.f[2]
        a.f[3] ~ n[3] * b.f[3]
        a.f[4] ~ n[4] * b.f[4]
        a.f[5] ~ n[5] * b.f[5]
        a.f[6] ~ n[6] * b.f[6]
        b.e[1] ~ -n[1] * a.e[1]
        b.e[2] ~ -n[2] * a.e[2]
        b.e[3] ~ -n[3] * a.e[3]
        b.e[4] ~ -n[4] * a.e[4]
        b.e[5] ~ -n[5] * a.e[5]
        b.e[6] ~ -n[6] * a.e[6]
    end
    @causality (a, b) => :transformer
end
