@block TFPlanar begin
    # Planar transformer: `stdlib:multibond/TFPlanar` is the planar `TF` of the plan's element
    # list (the `Planar` suffix avoids a catalog-name collision with the scalar
    # `stdlib:bondgraph/TF`).
    #
    # The modulus is a **diagonal** `Vec{3}` `n` (dimensionless): `a.f[k] = n[k]*b.f[k]` and
    # `b.e[k] = -n[k]*a.e[k]`, so `a.e . a.f + b.e . b.f = 0` for every component. A general
    # 3x3 matrix transformer is deliberately not offered here: the matrix form needs an
    # inverse transpose to express the reverse direction (the equation layer has no `inv`),
    # and v1 cannot write a whole-matrix transformer that is invertible per component. The
    # diagonal keeps every component independently invertible, and its modulus is a genuine
    # dimensionless ratio per axis. The matrix case that needs no inverse is `GYPlanar`
    # (`a.e = G*b.f`, `b.e = -G^T*a.f`) and the pose adjoint `TFAd`.
    #
    # `n` is declared with the dimensionless unit "1" (not left unitless), so the unit
    # checker still proves that each port keeps its own component unit through the element:
    # the torque stays a torque and the force stays a force.
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @parameters begin
        n::Vec{3} = [1.0, 1.0, 1.0], [unit = "1", description = "Diagonal transformer modulus per component"]
    end
    @equations begin
        a.f[1] ~ n[1] * b.f[1]
        a.f[2] ~ n[2] * b.f[2]
        a.f[3] ~ n[3] * b.f[3]
        b.e[1] ~ -n[1] * a.e[1]
        b.e[2] ~ -n[2] * a.e[2]
        b.e[3] ~ -n[3] * a.e[3]
    end
    @causality (a, b) => :transformer
end
