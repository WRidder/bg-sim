@block MGYSpatial begin
    # Modulated spatial gyrator: the 6x6 gyrator matrix is the signal input `G`, wired
    # component-wise as `G[1,1]` ... `G[6,6]`, so a controller can vary the coupling at run
    # time. The equations are `GYSpatial`'s: `a.e = G*b.f` and `b.e = -G^T*a.f`, written out
    # component-wise; the power identity holds for every `G`, so no inverse is needed. `G` is
    # declared without a unit for the reason documented in `GYSpatial` (a general spatial
    # gyrator matrix is not unit-homogeneous).
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @inputs G::Mat{6,6}, [description = "Gyrator matrix input G (a.e = G*b.f, b.e = -G^T*a.f)"]
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
