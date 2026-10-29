@block ExternalWrenchSpatial begin
    # External spatial wrench source: six scalar signal inputs with their own units
    # (N*m, N*m, N*m, N, N, N), in the port frame. The inputs are the **physical external
    # wrench** `W_ext` acting on the body, and the port effort is `p.e[k] = -w[k]`, the same
    # sign algebra as `ExternalWrenchPlanar` and `SeSpatial` (FIX-MB-4).
    #
    # For a body on a 1-junction the junction sums the efforts of its bonds to zero, so the
    # inertia feels `+W_ext` and `dP/dt = ad(V)^T P + W_ext`. Bonding the element directly to
    # the inertia gives `dP/dt = -w`; the sign is the enclosing junction's, as for every
    # bond-graph source. The input is the physical wrench so no caller has to negate it.
    @ports p::Power{Spatial}
    @inputs begin
        tx::Real, [unit = "N*m", description = "External torque about x (physical wrench about the port frame origin)"]
        ty::Real, [unit = "N*m", description = "External torque about y (physical wrench)"]
        tz::Real, [unit = "N*m", description = "External torque about z (physical wrench)"]
        fx::Real, [unit = "N", description = "External force x (physical wrench)"]
        fy::Real, [unit = "N", description = "External force y (physical wrench)"]
        fz::Real, [unit = "N", description = "External force z (physical wrench)"]
    end
    @equations begin
        p.e[1] ~ -tx
        p.e[2] ~ -ty
        p.e[3] ~ -tz
        p.e[4] ~ -fx
        p.e[5] ~ -fy
        p.e[6] ~ -fz
    end
    @causality p => (:effort_out, :fixed)
end
