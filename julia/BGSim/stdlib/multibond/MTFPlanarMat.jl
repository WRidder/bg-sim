@block MTFPlanarMat begin
    # Modulated planar **matrix** transformer: `stdlib:multibond/MTFPlanarMat` is the general
    # 3x3 form of `MTFPlanar`. The matrix is the signal input `M::Mat{3,3}` (wired
    # component-wise as `M[1,1]` … `M[3,3]`), so a controller can vary the coupling at run
    # time. The equations are the constant block's:
    #
    #     a.f = M b.f,        b.e = -M^T a.e,
    #
    # component-wise and power-continuous for every `M` (`a.e . a.f + b.e . b.f = 0`), so the
    # element never inverts `M`. `M` carries no unit for the reason documented in
    # `TFPlanarMat`/`GYPlanar`; the diagonal, unit-homogeneous modulation is `MTFPlanar`.
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @inputs M::Mat{3,3}, [description = "Transformer matrix input M (a.f = M*b.f, b.e = -M^T*a.e)"]
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
