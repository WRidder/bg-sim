@block ExternalWrenchPlanar begin
    # External planar wrench source: `stdlib:multibond/ExternalWrenchPlanar` is the plan's
    # `ExternalWrench` element for the planar domain.
    #
    # The wrench is supplied as three *scalar* signal inputs with their own units (N*m, N, N),
    # in the port's frame, and the inputs are the **physical external wrench** `W_ext` that
    # acts on the body. The port effort is that wrench, `p.e[k] = w[k]`: an effort source in
    # the convention of `SePlanar`/`MSePlanar` and `GravityPlanar`. On a body,
    # `dP/dt = ad(V)^T P + W_ext`.
    @ports p::Power{Planar}
    @inputs begin
        wr::Real, [unit = "N*m", description = "External torque (physical wrench about the port frame origin)"]
        wx::Real, [unit = "N", description = "External force x (physical wrench)"]
        wy::Real, [unit = "N", description = "External force y (physical wrench)"]
    end
    @equations begin
        p.e[1] ~ wr
        p.e[2] ~ wx
        p.e[3] ~ wy
    end
    @causality p => (:effort_out, :fixed)
    @orientation p => :out
end
