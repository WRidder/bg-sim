@block ExternalWrenchSpatial begin
    # External spatial wrench source: six scalar signal inputs with their own units
    # (N*m, N*m, N*m, N, N, N), in the port frame. The inputs are the **physical external
    # wrench** `W_ext` acting on the body, and the port effort is that wrench, `p.e[k] = w[k]`:
    # an effort source in the convention of `SeSpatial`, `GravitySpatial` and
    # `ExternalWrenchPlanar`. On a body, `dP/dt = ad(V)^T P + W_ext`.
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
        p.e[1] ~ tx
        p.e[2] ~ ty
        p.e[3] ~ tz
        p.e[4] ~ fx
        p.e[5] ~ fy
        p.e[6] ~ fz
    end
    @causality p => (:effort_out, :fixed)
    @orientation p => :out
end
