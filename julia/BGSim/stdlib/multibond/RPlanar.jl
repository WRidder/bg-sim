@block RPlanar begin
    # Planar resistive element: `stdlib:multibond/RPlanar` is the planar `R` of the plan's
    # element list (the `Planar` suffix avoids a catalog-name collision with the scalar
    # `stdlib:bondgraph/R`).
    #
    # One parameter per component because the components carry different units: a torsional
    # damping in N*m*s/rad and two translational ones in N*s/m (D-MB2/D-MB10). The effort is
    # `p.e[k] = b[k]*p.f[k]`, so the dissipated power is `p.e . p.f = sum_k b[k]*p.f[k]^2`,
    # which is never negative for `b >= 0`.
    #
    # No `@causality` declaration: like the scalar R, a resistor is free (SCAP may put the
    # stroke on either end; W202 is the designed report when a loop forces the choice).
    @ports p::Power{Planar}
    @parameters begin
        br::Real = 0.1, [unit = "N*m*s/rad", min = 0, description = "Angular damping"]
        bx::Real = 0.1, [unit = "N*s/m", min = 0, description = "Translational damping x"]
        by::Real = 0.1, [unit = "N*s/m", min = 0, description = "Translational damping y"]
    end
    @equations begin
        p.e[1] ~ br * p.f[1]
        p.e[2] ~ bx * p.f[2]
        p.e[3] ~ by * p.f[3]
    end
end
