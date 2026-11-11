@block SfSpatial begin
    # Spatial flow source (the spatial `Sf`): delivers the `Vec{6}` twist `u` with fixed
    # flow-out causality. Port flows count into the block, so it imposes `p.f = -u` (as the
    # scalar `Sf` and `SfPlanar`). The port components keep their own units (`p.f[1]` rad/s,
    # `p.f[4]` m/s, D-MB10).
    #
    # Limitation (v1 contract deviation, ADR-MB1 "M3 final"): a `Vec{6}` signal has one unit slot in v1, so the
    # twist *input* `u` is unit-homogeneous in the catalog and the manifest cannot show an
    # angular rate next to a linear one for it. The power port is per-component (asserted in
    # `test_spatial_slice.jl`); a per-component signal declaration is a contract change that
    # C-MB2 recorded as a v1 deviation (ADR-MB1, "M3 final").
    @ports p::Power{Spatial}
    @inputs u::Vec{6}
    @equations begin
        p.f[1] ~ -u[1]
        p.f[2] ~ -u[2]
        p.f[3] ~ -u[3]
        p.f[4] ~ -u[4]
        p.f[5] ~ -u[5]
        p.f[6] ~ -u[6]
    end
    @causality p => (:flow_out, :fixed)
    @orientation p => :out
end
