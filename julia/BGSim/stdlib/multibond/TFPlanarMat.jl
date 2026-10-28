@block TFPlanarMat begin
    # Planar **matrix** transformer: `stdlib:multibond/TFPlanarMat` is the general 3x3 form of
    # the planar `TF`. `TFPlanar` keeps the diagonal `Vec{3}` modulus (the unit-homogeneous
    # case, where each component stays its own unit); this block is the full coupling
    #
    #     a.f = M b.f,        b.e = -M^T a.e,
    #
    # written component-wise. With those two relations
    # `a.e . a.f + b.e . b.f = (M^T a.e)^T b.f - (M^T a.e)^T b.f = 0` identically, so **no
    # inverse is needed** and the element is power-continuous for every `M`. The reverse
    # spelling (`b.f = M^-1 a.f` with the dual `a.e = M^-T b.e`) is algebraically identical but
    # would need the inverse; it is never written, so the block is explicit in the flow-in-at-b
    # / effort-in-at-a orientation, exactly like `TFPlanar`. `MTFPlanarMat` is the modulated
    # form.
    #
    # Unit note (same as `GYPlanar`): a general planar matrix is **not unit-homogeneous** (its
    # rotational/translational blocks differ by a length), and a `Mat` declaration carries one
    # `unit` slot for all nine entries, so `M` is declared without a unit: the products are
    # unit wildcards instead of a wrong unit (D-MB10 defers vector-valued unit inference). The
    # ports keep their own per-component units (`a.e[1]` is N*m, `a.e[2]` is N), which is what
    # the manifest and the editor show. A dimensionless diagonal modulus is `TFPlanar`.
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @parameters begin
        M::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Transformer matrix M (a.f = M*b.f, b.e = -M^T*a.e)"]
    end
    @equations begin
        a.f[1] ~ M[1, 1] * b.f[1] + M[1, 2] * b.f[2] + M[1, 3] * b.f[3]
        a.f[2] ~ M[2, 1] * b.f[1] + M[2, 2] * b.f[2] + M[2, 3] * b.f[3]
        a.f[3] ~ M[3, 1] * b.f[1] + M[3, 2] * b.f[2] + M[3, 3] * b.f[3]
        b.e[1] ~ -(M[1, 1] * a.e[1] + M[2, 1] * a.e[2] + M[3, 1] * a.e[3])
        b.e[2] ~ -(M[1, 2] * a.e[1] + M[2, 2] * a.e[2] + M[3, 2] * a.e[3])
        b.e[3] ~ -(M[1, 3] * a.e[1] + M[2, 3] * a.e[2] + M[3, 3] * a.e[3])
    end
    @causality (a, b) => :transformer
end
