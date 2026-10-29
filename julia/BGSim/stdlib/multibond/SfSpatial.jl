@block SfSpatial begin
    # Spatial flow source (the spatial `Sf`): imposes a `Vec{6}` twist on its bond with fixed
    # flow-out causality. Like `SfPlanar` the input is one `Vec{6}` signal; the port
    # components keep their own units (`p.f[1]` rad/s, `p.f[4]` m/s, D-MB10).
    #
    # Limitation (C-MB2 contract gap): a `Vec{6}` signal has one unit slot in v1, so the
    # twist *input* `u` is unit-homogeneous in the catalog and the manifest cannot show an
    # angular rate next to a linear one for it. The power port is per-component (asserted in
    # `test_spatial_slice.jl`); a per-component signal declaration is a contract change owned
    # by C-MB2.
    @ports p::Power{Spatial}
    @inputs u::Vec{6}
    @equations begin
        p.f[1] ~ u[1]
        p.f[2] ~ u[2]
        p.f[3] ~ u[3]
        p.f[4] ~ u[4]
        p.f[5] ~ u[5]
        p.f[6] ~ u[6]
    end
    @causality p => (:flow_out, :fixed)
end
