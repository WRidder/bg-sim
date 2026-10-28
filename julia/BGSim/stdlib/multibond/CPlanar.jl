@block CPlanar begin
    # Planar capacitive storage: `stdlib:multibond/CPlanar` is the planar `C` of the plan's
    # element list (the `Planar` suffix avoids a catalog-name collision with the scalar
    # `stdlib:bondgraph/C`).
    #
    # The state is three scalars, not a `Vec{3}`: a vector declaration is unit-homogeneous in
    # v1 (one `unit` attribute for the whole array), while a planar capacitance stores an
    # angular displacement in rad next to two linear ones in m. Three scalars keep the units
    # honest (D-MB2/D-MB10); a `Vec{3}` state would be checked as three of the same unit.
    #
    # Integral (effort-out) causality by preference, exactly like the scalar C: the flow is
    # the input, `ddt(q[k]) = p.f[k]`, and the effort is the spring law
    # `p.e[k] = k[k]*(q[k] - q0[k])` with the rest deflection defaulting to zero.
    @ports p::Power{Planar}
    @parameters begin
        kr::Real = 1.0, [unit = "N*m/rad", min = 0, description = "Angular stiffness"]
        kx::Real = 1.0, [unit = "N/m", min = 0, description = "Translational stiffness x"]
        ky::Real = 1.0, [unit = "N/m", min = 0, description = "Translational stiffness y"]
        qr0::Real = 0.0, [unit = "rad", description = "Angular rest deflection"]
        qx0::Real = 0.0, [unit = "m", description = "Linear rest deflection x"]
        qy0::Real = 0.0, [unit = "m", description = "Linear rest deflection y"]
    end
    @variables begin
        qr::Real = 0.0, [unit = "rad", state = :prefer, description = "Angular displacement"]
        qx::Real = 0.0, [unit = "m", state = :prefer, description = "Linear displacement x"]
        qy::Real = 0.0, [unit = "m", state = :prefer, description = "Linear displacement y"]
    end
    @equations begin
        ddt(qr) ~ p.f[1]
        ddt(qx) ~ p.f[2]
        ddt(qy) ~ p.f[3]
        p.e[1] ~ kr * (qr - qr0)
        p.e[2] ~ kx * (qx - qx0)
        p.e[3] ~ ky * (qy - qy0)
    end
    @causality p => :effort_out
end
