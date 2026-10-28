@block MSePlanar begin
    # Modulated planar effort source: `stdlib:multibond/MSePlanar` is the planar `MSe` of the
    # plan's element list (the `Planar` suffix avoids a catalog-name collision with the
    # scalar `stdlib:bondgraph/MSe`).
    #
    # Three *scalar* signal inputs, not one `Vec{3}`: a vector signal is unit-homogeneous in
    # v1, but the wrench components are a torque (N*m) and two forces (N) (D-MB2/D-MB10). The
    # effort is imposed component by component, with the fixed effort-out causality of a
    # source.
    @ports p::Power{Planar}
    @inputs begin
        ur::Real, [unit = "N*m"]
        ux::Real, [unit = "N"]
        uy::Real, [unit = "N"]
    end
    @equations begin
        p.e[1] ~ ur
        p.e[2] ~ ux
        p.e[3] ~ uy
    end
    @causality p => (:effort_out, :fixed)
end
