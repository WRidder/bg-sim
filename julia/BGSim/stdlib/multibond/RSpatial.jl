@block RSpatial begin
    # Spatial resistive element (the spatial `R`): one damping coefficient per component
    # because a torsional damping (N*m*s/rad) and a translational one (N*s/m) do not share a
    # unit (D-MB2/D-MB10). The effort is `p.e[k] = b[k]*p.f[k]`, so the dissipated power
    # `p.e . p.f = sum_k b[k]*p.f[k]^2` is never negative for `b >= 0`.
    #
    # No `@causality` declaration: like the scalar `R`, a resistor is free (SCAP may put the
    # stroke on either end; W202 is the designed report when a loop forces the choice).
    @ports p::Power{Spatial}
    @parameters begin
        brx::Real = 0.1, [unit = "N*m*s/rad", min = 0, description = "Torsional damping about x"]
        bry::Real = 0.1, [unit = "N*m*s/rad", min = 0, description = "Torsional damping about y"]
        brz::Real = 0.1, [unit = "N*m*s/rad", min = 0, description = "Torsional damping about z"]
        bx::Real = 0.1, [unit = "N*s/m", min = 0, description = "Translational damping x"]
        by::Real = 0.1, [unit = "N*s/m", min = 0, description = "Translational damping y"]
        bz::Real = 0.1, [unit = "N*s/m", min = 0, description = "Translational damping z"]
    end
    @equations begin
        p.e[1] ~ brx * p.f[1]
        p.e[2] ~ bry * p.f[2]
        p.e[3] ~ brz * p.f[3]
        p.e[4] ~ bx * p.f[4]
        p.e[5] ~ by * p.f[5]
        p.e[6] ~ bz * p.f[6]
    end
end
