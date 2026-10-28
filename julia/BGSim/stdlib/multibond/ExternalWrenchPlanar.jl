@block ExternalWrenchPlanar begin
    # External planar wrench source: `stdlib:multibond/ExternalWrenchPlanar` is the plan's
    # `ExternalWrench` element for the planar domain.
    #
    # The wrench is supplied as three *scalar* signal inputs with their own units (N*m, N, N),
    # in the port's frame: `p.e[k] = w[k]`. This is an effort source in the exact convention
    # of `SePlanar`/`MSePlanar`, so it is the wrench the element supplies to the junction.
    #
    # Sign, for a body on a 1-junction: the junction sums the efforts of its bonds to zero, so
    # an inertia whose port effort is `e_I` sees `e_I = -(e_gravity + e_coriolis + w)`. The
    # body therefore feels `-w`: to apply a physical external wrench `W_ext` to the body,
    # drive the input with `w = -W_ext` (the same sign convention as `GravityPlanar`, whose
    # port effort is `-W_gravity`). Bonding the element directly to the inertia gives
    # `dP/dt = +w`; the sign is the enclosing junction's, as for every bond-graph source.
    @ports p::Power{Planar}
    @inputs begin
        wr::Real, [unit = "N*m"]
        wx::Real, [unit = "N"]
        wy::Real, [unit = "N"]
    end
    @equations begin
        p.e[1] ~ wr
        p.e[2] ~ wx
        p.e[3] ~ wy
    end
    @causality p => (:effort_out, :fixed)
end
