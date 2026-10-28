@block GYPlanar begin
    # Planar gyrator: `stdlib:multibond/GYPlanar` is the planar `GY` of the plan's element list
    # (the `Planar` suffix avoids a catalog-name collision with the scalar
    # `stdlib:bondgraph/GY`).
    #
    # A full 3x3 matrix gyrator. With `a.e = G*b.f` and `b.e = -G^T*a.f`,
    # `a.e . a.f + b.e . b.f = (G b.f)^T a.f - (G^T a.f)^T b.f = 0` identically, so no inverse
    # is needed and the element is power-continuous for every `G`. The second row below is
    # the transpose written out component-wise (there is no whole-matrix `transpose` on the
    # equation path and D-MB10 wants `[k]` terms), i.e. `(G^T a.f)[k] = sum_j G[j,k] a.f[j]`.
    #
    # Unit note: the three planar components are not unit-homogeneous (a torque next to two
    # forces, D-MB2), so a general `G` has no single unit for its nine entries (its
    # rotational/translational blocks differ by a length). A `Mat` declaration can carry only
    # one `unit` attribute, so `G` is declared without one: the products are unit wildcards
    # and the scalar checker does not invent a wrong unit (D-MB10 defers vector-valued unit
    # inference). The ports keep their own per-component units (`a.e[1]` is N*m,
    # `a.e[2]` is N), which is what the manifest and the editor show; a unit-homogeneous
    # diagonal modulus is available as `TFPlanar`, and `GYPlanar`'s power identity is tested
    # numerically for random `G`.
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @parameters begin
        G::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Gyrator matrix G (a.e = G*b.f, b.e = -G^T*a.f)"]
    end
    @equations begin
        a.e[1] ~ G[1, 1] * b.f[1] + G[1, 2] * b.f[2] + G[1, 3] * b.f[3]
        a.e[2] ~ G[2, 1] * b.f[1] + G[2, 2] * b.f[2] + G[2, 3] * b.f[3]
        a.e[3] ~ G[3, 1] * b.f[1] + G[3, 2] * b.f[2] + G[3, 3] * b.f[3]
        b.e[1] ~ -(G[1, 1] * a.f[1] + G[2, 1] * a.f[2] + G[3, 1] * a.f[3])
        b.e[2] ~ -(G[1, 2] * a.f[1] + G[2, 2] * a.f[2] + G[3, 2] * a.f[3])
        b.e[3] ~ -(G[1, 3] * a.f[1] + G[2, 3] * a.f[2] + G[3, 3] * a.f[3])
    end
    @causality (a, b) => :gyrator
end
