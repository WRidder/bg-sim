@block DfSpatial begin
    # Spatial flow detector (the spatial `Df`): imposes zero wrench, outputs the six twist
    # components.
    #
    # Limitation (C-MB2 contract gap, same as `SfSpatial`): the output `y` is one `Vec{6}`
    # signal with a single unit slot, so the manifest shows no per-component unit for it even
    # though `y[1]` is an angular rate and `y[4]` a linear one. The power port `p.f[k]` keeps
    # its per-component units (asserted in `test_spatial_slice.jl`).
    @ports p::Power{Spatial}
    @outputs y::Vec{6}
    @equations begin
        p.e[1] ~ 0.0
        p.e[2] ~ 0.0
        p.e[3] ~ 0.0
        p.e[4] ~ 0.0
        p.e[5] ~ 0.0
        p.e[6] ~ 0.0
        y[1] ~ p.f[1]
        y[2] ~ p.f[2]
        y[3] ~ p.f[3]
        y[4] ~ p.f[4]
        y[5] ~ p.f[5]
        y[6] ~ p.f[6]
    end
    @causality p => (:effort_out, :fixed)
end
