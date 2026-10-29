@block CoriolisSpatial begin
    # Eulerian junction structure of a spatial body (Breedveld), the spatial `Coriolis` of the
    # plan's element list: the port effort is the negative of the physical Coriolis/gyroscopic
    # wrench, `p.e = -ad(f)^T P`, with `f = [w; v]` the body twist and `P = [h; p]` the
    # momentum. The inertia lives only in `ISpatial` (D-MB3); the block reads `P` as a signal.
    #
    # Component-wise, with w = f[1:3], v = f[4:6], h = P[1:3], p = P[4:6]:
    #
    #     ad(V) = [[w_hat, 0], [v_hat, w_hat]]        (angular first, D-MB2)
    #     -ad(V)^T P = [ w x h + v x p ; w x p ]
    #
    # On a 1-junction the Coriolis bond carries the negative of the body twist, so the inertia
    # receives `+ad(V)^T P`: `dP/dt = ad(V)^T P (+ W_ext)`, the body-frame Euler equation. The
    # element's own power `p.e . p.f = -V^T ad(V)^T P` is zero because `ad(V) V = 0`; the
    # free-body run (momentum and energy, Dzhanibekov) is the acceptance test.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs P::Vec{6}
    @equations begin
        p.e[1] ~ p.f[2] * P[3] - p.f[3] * P[2] + p.f[5] * P[6] - p.f[6] * P[5]
        p.e[2] ~ p.f[3] * P[1] - p.f[1] * P[3] + p.f[6] * P[4] - p.f[4] * P[6]
        p.e[3] ~ p.f[1] * P[2] - p.f[2] * P[1] + p.f[4] * P[5] - p.f[5] * P[4]
        p.e[4] ~ p.f[2] * P[6] - p.f[3] * P[5]
        p.e[5] ~ p.f[3] * P[4] - p.f[1] * P[6]
        p.e[6] ~ p.f[1] * P[5] - p.f[2] * P[4]
    end
    @causality p => (:effort_out, :fixed)
end
