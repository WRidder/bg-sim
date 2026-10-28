@block CoriolisPlanar begin
    @ports p::Power{Planar}, [frame = "body"]
    @inputs P::Vec{3}
    @equations begin
        # Breedveld's Eulerian junction structure: e = ad(f)^T P with f = [w, vx, vy] and
        # P = [P1, P2, P3]. The inertia lives only in IPlanar (D-MB3); the identity
        # e . f = P . (ad(f) f) = 0 is the power test.
        p.e[1] ~ p.f[3] * P[2] - p.f[2] * P[3]
        p.e[2] ~ p.f[1] * P[3]
        p.e[3] ~ -p.f[1] * P[2]
    end
    @causality p => (:effort_out, :fixed)
end
