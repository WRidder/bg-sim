@block TFPlanar begin
    # Planar transformer: `stdlib:multibond/TFPlanar` is the planar `TF` of the plan's element
    # list (the `Planar` suffix avoids a catalog-name collision with the scalar
    # `stdlib:bondgraph/TF`).
    #
    # The modulus is a **diagonal** `Vec{3}` `n` (dimensionless): `a.f[k] = n[k]*b.f[k]` and
    # `b.e[k] = -n[k]*a.e[k]`, so `a.e . a.f + b.e . b.f = 0` for every component. The general
    # 3x3 matrix form is `TFPlanarMat` (`a.f = M b.f`, `b.e = -M^T a.e`, component-wise,
    # power-continuous for every `M` and needing no inverse); the diagonal variant is kept
    # because its modulus is a genuine dimensionless ratio per axis, so the unit checker
    # still proves that torque stays torque and force stays force through the element. A
    # matrix `M` is not unit-homogeneous (a `Mat` has one unit slot), which is why the matrix
    # block declares it without a unit (D-MB10).
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
