@block GYSpatial begin
    # Spatial gyrator (the spatial `GY`): a full 6x6 matrix gyrator. With `a.e = G*b.f` and
    # `b.e = -G^T*a.f`,
    # `a.e . a.f + b.e . b.f = (G b.f)^T a.f - (G^T a.f)^T b.f = 0` identically, so no inverse
    # is needed and the element is power-continuous for every `G`. The second group of rows is
    # the transpose written out component-wise (`(G^T a.f)[i] = sum_j G[j,i] a.f[j]`).
    #
    # Unit note: the six components are not unit-homogeneous (three torques and three forces,
    # D-MB2), so a general `G` has no single unit for its 36 entries (its
    # rotational/translational blocks differ by a length). A `Mat` declaration can carry only
    # one `unit` attribute, so `G` is declared without one: the products are unit wildcards
    # and the scalar checker does not invent a wrong unit (D-MB10). The ports keep their own
    # per-component units (`a.e[1]` N*m, `a.e[4]` N), and the power identity is tested
    # numerically for random `G`.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @parameters begin
        G::Mat{6,6} = [1.0 0.0 0.0 0.0 0.0 0.0;
                       0.0 1.0 0.0 0.0 0.0 0.0;
                       0.0 0.0 1.0 0.0 0.0 0.0;
                       0.0 0.0 0.0 1.0 0.0 0.0;
                       0.0 0.0 0.0 0.0 1.0 0.0;
                       0.0 0.0 0.0 0.0 0.0 1.0], [description = "Gyrator matrix G (a.e = G*b.f, b.e = -G^T*a.f)"]
    end
    @equations begin
        a.e[1] ~ G[1, 1] * b.f[1] + G[1, 2] * b.f[2] + G[1, 3] * b.f[3] +
                 G[1, 4] * b.f[4] + G[1, 5] * b.f[5] + G[1, 6] * b.f[6]
        a.e[2] ~ G[2, 1] * b.f[1] + G[2, 2] * b.f[2] + G[2, 3] * b.f[3] +
                 G[2, 4] * b.f[4] + G[2, 5] * b.f[5] + G[2, 6] * b.f[6]
        a.e[3] ~ G[3, 1] * b.f[1] + G[3, 2] * b.f[2] + G[3, 3] * b.f[3] +
                 G[3, 4] * b.f[4] + G[3, 5] * b.f[5] + G[3, 6] * b.f[6]
        a.e[4] ~ G[4, 1] * b.f[1] + G[4, 2] * b.f[2] + G[4, 3] * b.f[3] +
                 G[4, 4] * b.f[4] + G[4, 5] * b.f[5] + G[4, 6] * b.f[6]
        a.e[5] ~ G[5, 1] * b.f[1] + G[5, 2] * b.f[2] + G[5, 3] * b.f[3] +
                 G[5, 4] * b.f[4] + G[5, 5] * b.f[5] + G[5, 6] * b.f[6]
        a.e[6] ~ G[6, 1] * b.f[1] + G[6, 2] * b.f[2] + G[6, 3] * b.f[3] +
                 G[6, 4] * b.f[4] + G[6, 5] * b.f[5] + G[6, 6] * b.f[6]
        b.e[1] ~ -(G[1, 1] * a.f[1] + G[2, 1] * a.f[2] + G[3, 1] * a.f[3] +
                   G[4, 1] * a.f[4] + G[5, 1] * a.f[5] + G[6, 1] * a.f[6])
        b.e[2] ~ -(G[1, 2] * a.f[1] + G[2, 2] * a.f[2] + G[3, 2] * a.f[3] +
                   G[4, 2] * a.f[4] + G[5, 2] * a.f[5] + G[6, 2] * a.f[6])
        b.e[3] ~ -(G[1, 3] * a.f[1] + G[2, 3] * a.f[2] + G[3, 3] * a.f[3] +
                   G[4, 3] * a.f[4] + G[5, 3] * a.f[5] + G[6, 3] * a.f[6])
        b.e[4] ~ -(G[1, 4] * a.f[1] + G[2, 4] * a.f[2] + G[3, 4] * a.f[3] +
                   G[4, 4] * a.f[4] + G[5, 4] * a.f[5] + G[6, 4] * a.f[6])
        b.e[5] ~ -(G[1, 5] * a.f[1] + G[2, 5] * a.f[2] + G[3, 5] * a.f[3] +
                   G[4, 5] * a.f[4] + G[5, 5] * a.f[5] + G[6, 5] * a.f[6])
        b.e[6] ~ -(G[1, 6] * a.f[1] + G[2, 6] * a.f[2] + G[3, 6] * a.f[3] +
                   G[4, 6] * a.f[4] + G[5, 6] * a.f[5] + G[6, 6] * a.f[6])
    end
    @causality (a, b) => :gyrator
end
