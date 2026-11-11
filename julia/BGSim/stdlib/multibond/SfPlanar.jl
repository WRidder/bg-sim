@block SfPlanar begin
    # Planar flow source (the planar `Sf`). Port flows count into the block, so a source that
    # delivers the twist `u` imposes `p.f = -u` (as the scalar `Sf`).
    @ports p::Power{Planar}
    @inputs u::Vec{3}
    @equations begin
        p.f[1] ~ -u[1]
        p.f[2] ~ -u[2]
        p.f[3] ~ -u[3]
    end
    @causality p => (:flow_out, :fixed)
    @orientation p => :out
end
