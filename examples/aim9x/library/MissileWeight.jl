@block MissileWeight begin
    # Weight of a variable-mass missile as a body-frame wrench (for `ExternalWrenchSpatial`):
    # W = m(t) R^T (0, 0, -g0), no torque about the centre of mass. The stdlib `GravitySpatial`
    # has the mass as a parameter; this is its modulated twin, used because the missile burns
    # 21 kg of propellant in 2.4 s.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z)"]
        m::Real, [unit = "kg", description = "Current mass"]
    end
    @parameters g0::Real = 9.80665, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    @variables s::Real = 1.0, [description = "Squared quaternion norm"]
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        tx ~ 0.0
        ty ~ 0.0
        tz ~ 0.0
        fx ~ -2 * m * g0 * (g[2] * g[4] - g[1] * g[3]) / s
        fy ~ -2 * m * g0 * (g[3] * g[4] + g[1] * g[2]) / s
        fz ~ -m * g0 * (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
    end
end
