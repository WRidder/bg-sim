@block TFSpatialMat begin
    # Spatial **matrix** transformer: the general 6x6 form of the spatial `TF`,
    #
    #     a.f = M b.f,        b.e = -M^T a.e,
    #
    # written component-wise. With those two relations
    # `a.e . a.f + b.e . b.f = (M^T a.e)^T b.f - (M^T a.e)^T b.f = 0` identically, so **no
    # inverse is ever written** and the element is power-continuous for every `M` (the same
    # argument as `TFPlanarMat`). The reverse spelling (`b.f = M^-1 a.f` with the dual
    # `a.e = M^-T b.e`) is algebraically identical but would need the inverse; it is never
    # written, so the block is explicit in the flow-in-at-b / effort-in-at-a orientation.
    #
    # Unit note (same as `TFSpatial`'s matrix sibling `GYPlanar`): a general spatial matrix is
    # **not** unit-homogeneous (its rotational/translational blocks differ by a length), and a
    # `Mat` declaration carries one `unit` slot for all entries, so `M` is declared without a
    # unit: the products are unit wildcards instead of a wrong unit (D-MB10 defers
    # vector-valued unit inference). The ports keep their own per-component units, and the
    # dimensionless diagonal modulus of `TFSpatial` keeps the component-by-component unit
    # proof alive through a transformer.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @parameters begin
        M::Mat{6,6} = [1.0 0.0 0.0 0.0 0.0 0.0;
                       0.0 1.0 0.0 0.0 0.0 0.0;
                       0.0 0.0 1.0 0.0 0.0 0.0;
                       0.0 0.0 0.0 1.0 0.0 0.0;
                       0.0 0.0 0.0 0.0 1.0 0.0;
                       0.0 0.0 0.0 0.0 0.0 1.0], [description = "Transformer matrix M (a.f = M*b.f, b.e = -M^T*a.e)"]
    end
    @equations begin
        a.f[1] ~ M[1, 1] * b.f[1] + M[1, 2] * b.f[2] + M[1, 3] * b.f[3] +
                 M[1, 4] * b.f[4] + M[1, 5] * b.f[5] + M[1, 6] * b.f[6]
        a.f[2] ~ M[2, 1] * b.f[1] + M[2, 2] * b.f[2] + M[2, 3] * b.f[3] +
                 M[2, 4] * b.f[4] + M[2, 5] * b.f[5] + M[2, 6] * b.f[6]
        a.f[3] ~ M[3, 1] * b.f[1] + M[3, 2] * b.f[2] + M[3, 3] * b.f[3] +
                 M[3, 4] * b.f[4] + M[3, 5] * b.f[5] + M[3, 6] * b.f[6]
        a.f[4] ~ M[4, 1] * b.f[1] + M[4, 2] * b.f[2] + M[4, 3] * b.f[3] +
                 M[4, 4] * b.f[4] + M[4, 5] * b.f[5] + M[4, 6] * b.f[6]
        a.f[5] ~ M[5, 1] * b.f[1] + M[5, 2] * b.f[2] + M[5, 3] * b.f[3] +
                 M[5, 4] * b.f[4] + M[5, 5] * b.f[5] + M[5, 6] * b.f[6]
        a.f[6] ~ M[6, 1] * b.f[1] + M[6, 2] * b.f[2] + M[6, 3] * b.f[3] +
                 M[6, 4] * b.f[4] + M[6, 5] * b.f[5] + M[6, 6] * b.f[6]
        b.e[1] ~ -(M[1, 1] * a.e[1] + M[2, 1] * a.e[2] + M[3, 1] * a.e[3] +
                   M[4, 1] * a.e[4] + M[5, 1] * a.e[5] + M[6, 1] * a.e[6])
        b.e[2] ~ -(M[1, 2] * a.e[1] + M[2, 2] * a.e[2] + M[3, 2] * a.e[3] +
                   M[4, 2] * a.e[4] + M[5, 2] * a.e[5] + M[6, 2] * a.e[6])
        b.e[3] ~ -(M[1, 3] * a.e[1] + M[2, 3] * a.e[2] + M[3, 3] * a.e[3] +
                   M[4, 3] * a.e[4] + M[5, 3] * a.e[5] + M[6, 3] * a.e[6])
        b.e[4] ~ -(M[1, 4] * a.e[1] + M[2, 4] * a.e[2] + M[3, 4] * a.e[3] +
                   M[4, 4] * a.e[4] + M[5, 4] * a.e[5] + M[6, 4] * a.e[6])
        b.e[5] ~ -(M[1, 5] * a.e[1] + M[2, 5] * a.e[2] + M[3, 5] * a.e[3] +
                   M[4, 5] * a.e[4] + M[5, 5] * a.e[5] + M[6, 5] * a.e[6])
        b.e[6] ~ -(M[1, 6] * a.e[1] + M[2, 6] * a.e[2] + M[3, 6] * a.e[3] +
                   M[4, 6] * a.e[4] + M[5, 6] * a.e[5] + M[6, 6] * a.e[6])
    end
    @causality (a, b) => :transformer
end
