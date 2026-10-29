@block DeSpatial begin
    # Spatial effort detector (the spatial `De`): imposes zero twist, outputs the six wrench
    # components.
    #
    # Limitation (C-MB2 contract gap, same as `SeSpatial`): the output `y` is one `Vec{6}`
    # signal with a single unit slot, so the manifest shows no per-component unit for it even
    # though `y[1]` is a torque and `y[4]` a force. The power port `p.e[k]` keeps its
    # per-component units (asserted in `test_spatial_slice.jl`).
    @ports p::Power{Spatial}
    @outputs y::Vec{6}
    @equations begin
        p.f[1] ~ 0.0
        p.f[2] ~ 0.0
        p.f[3] ~ 0.0
        p.f[4] ~ 0.0
        p.f[5] ~ 0.0
        p.f[6] ~ 0.0
        y[1] ~ p.e[1]
        y[2] ~ p.e[2]
        y[3] ~ p.e[3]
        y[4] ~ p.e[4]
        y[5] ~ p.e[5]
        y[6] ~ p.e[6]
    end
    @causality p => (:flow_out, :fixed)
end
