@block MSfPlanar begin
    # Modulated planar flow source: `stdlib:multibond/MSfPlanar` is the planar `MSf` of the
    # plan's element list (the `Planar` suffix avoids a catalog-name collision with the
    # scalar `stdlib:bondgraph/MSf`).
    #
    # Three *scalar* signal inputs, not one `Vec{3}`: a vector signal is unit-homogeneous in
    # v1, but a twist is an angular rate (rad/s) and two linear velocities (m/s)
    # (D-MB2/D-MB10). The flow is imposed component by component, with the fixed flow-out
    # causality of a source.
    @ports p::Power{Planar}
    @inputs begin
        vr::Real, [unit = "rad/s"]
        vx::Real, [unit = "m/s"]
        vy::Real, [unit = "m/s"]
    end
    @equations begin
        p.f[1] ~ vr
        p.f[2] ~ vx
        p.f[3] ~ vy
    end
    @causality p => (:flow_out, :fixed)
end
