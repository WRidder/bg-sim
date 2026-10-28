@block ExternalWrenchPlanar begin
    # External planar wrench source: `stdlib:multibond/ExternalWrenchPlanar` is the plan's
    # `ExternalWrench` element for the planar domain.
    #
    # The wrench is supplied as three *scalar* signal inputs with their own units (N*m, N, N),
    # in the port's frame, and the inputs are the **physical external wrench** `W_ext` that
    # acts on the body. The port effort is `p.e[k] = -w[k]`: this is an effort source in the
    # exact convention of `SePlanar`/`MSePlanar`, where the port effort is the wrench the
    # element supplies *to* the junction.
    #
    # Sign, for a body on a 1-junction: the junction sums the efforts of its bonds to zero, so
    # an inertia whose port effort is `e_I` sees `e_I = -(e_gravity + e_coriolis + p.e)`. The
    # body therefore feels `+w`: driving the inputs with the physical external wrench
    # `W_ext = (tau, fx, fy)` gives `dP/dt = +W_ext`. (The element still supplies `-W_ext` to
    # the junction, the same sign algebra as `GravityPlanar`, whose port effort is
    # `-W_gravity`.) Bonding the element directly to the inertia gives `dP/dt = -w`; the sign
    # is the enclosing junction's, as for every bond-graph source. The input is the physical
    # wrench so no caller has to negate it (FIX-MB-4; the pre-fix version named the input `w`
    # but used `p.e = w`, which made a body on a 1-junction feel `-W_ext`).
    @ports p::Power{Planar}
    @inputs begin
        wr::Real, [unit = "N*m", description = "External torque (physical wrench about the port frame origin)"]
        wx::Real, [unit = "N", description = "External force x (physical wrench)"]
        wy::Real, [unit = "N", description = "External force y (physical wrench)"]
    end
    @equations begin
        p.e[1] ~ -wr
        p.e[2] ~ -wx
        p.e[3] ~ -wy
    end
    @causality p => (:effort_out, :fixed)
end
