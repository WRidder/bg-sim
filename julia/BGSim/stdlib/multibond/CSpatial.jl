@block CSpatial begin
    # Spatial capacitive storage (the spatial `C`): six scalar displacement states, not one
    # `Vec{6}`, because a spatial capacitance holds an angular displacement in rad beside
    # three linear ones in m and a vector declaration is unit-homogeneous in v1 (D-MB2,
    # D-MB10). The stiffnesses keep their own units too: N*m/rad torsional, N/m linear.
    #
    # Integral (effort-out) causality by preference, like the scalar `C`: the flow is the
    # input, `ddt(q[k]) = p.f[k]`, and the effort is the spring law
    # `p.e[k] = k[k]*(q[k] - q0[k])` with a zero rest deflection by default.
    @ports p::Power{Spatial}
    @parameters begin
        krx::Real = 1.0, [unit = "N*m/rad", min = 0, description = "Torsional stiffness about x"]
        kry::Real = 1.0, [unit = "N*m/rad", min = 0, description = "Torsional stiffness about y"]
        krz::Real = 1.0, [unit = "N*m/rad", min = 0, description = "Torsional stiffness about z"]
        kx::Real = 1.0, [unit = "N/m", min = 0, description = "Translational stiffness x"]
        ky::Real = 1.0, [unit = "N/m", min = 0, description = "Translational stiffness y"]
        kz::Real = 1.0, [unit = "N/m", min = 0, description = "Translational stiffness z"]
        qrx0::Real = 0.0, [unit = "rad", description = "Angular rest deflection about x"]
        qry0::Real = 0.0, [unit = "rad", description = "Angular rest deflection about y"]
        qrz0::Real = 0.0, [unit = "rad", description = "Angular rest deflection about z"]
        qx0::Real = 0.0, [unit = "m", description = "Linear rest deflection x"]
        qy0::Real = 0.0, [unit = "m", description = "Linear rest deflection y"]
        qz0::Real = 0.0, [unit = "m", description = "Linear rest deflection z"]
    end
    @variables begin
        qrx::Real = 0.0, [unit = "rad", state = :prefer, description = "Angular displacement about x"]
        qry::Real = 0.0, [unit = "rad", state = :prefer, description = "Angular displacement about y"]
        qrz::Real = 0.0, [unit = "rad", state = :prefer, description = "Angular displacement about z"]
        qx::Real = 0.0, [unit = "m", state = :prefer, description = "Linear displacement x"]
        qy::Real = 0.0, [unit = "m", state = :prefer, description = "Linear displacement y"]
        qz::Real = 0.0, [unit = "m", state = :prefer, description = "Linear displacement z"]
    end
    @equations begin
        ddt(qrx) ~ p.f[1]
        ddt(qry) ~ p.f[2]
        ddt(qrz) ~ p.f[3]
        ddt(qx) ~ p.f[4]
        ddt(qy) ~ p.f[5]
        ddt(qz) ~ p.f[6]
        p.e[1] ~ krx * (qrx - qrx0)
        p.e[2] ~ kry * (qry - qry0)
        p.e[3] ~ krz * (qrz - qrz0)
        p.e[4] ~ kx * (qx - qx0)
        p.e[5] ~ ky * (qy - qy0)
        p.e[6] ~ kz * (qz - qz0)
    end
    @causality p => :effort_out
end
