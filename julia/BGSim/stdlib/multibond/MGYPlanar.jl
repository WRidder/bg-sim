@block MGYPlanar begin
    # Modulated planar gyrator: `stdlib:multibond/MGYPlanar` is the planar `MGY` of the plan's
    # element list (the `Planar` suffix avoids a catalog-name collision with the scalar
    # `stdlib:bondgraph/MGY`).
    #
    # The gyrator matrix is the signal input `G::Mat{3,3}` (a matrix signal is wired
    # component-wise as `G[1,1]` … `G[3,3]`), so a controller can vary the coupling at run
    # time. The equations are `GYPlanar`'s: `a.e = G*b.f` and `b.e = -G^T*a.f`, written out
    # component-wise; the power identity holds for every `G`, so no inverse is needed. `G` is
    # declared without a unit for the reason documented in `GYPlanar` (a general planar
    # gyrator matrix is not unit-homogeneous).
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @inputs G::Mat{3,3}, [description = "Gyrator matrix input G (a.e = G*b.f, b.e = -G^T*a.f)"]
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
