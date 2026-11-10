@block CentralGravity3D begin
    # Inverse-square gravity of a spherical Earth on a body of variable mass, as a body wrench at
    # the centre of mass (for an `ExternalWrenchSpatial`). The world frame is the inertial launch
    # frame: origin on the pad, z up, the Earth's centre at (0, 0, -R). With the CoM at
    # rc = p + (0, 0, R) from the centre,
    #
    #     F_world = -scale mu m rc / |rc|^3,       F_body = R(q)^T F_world
    #
    # so g falls off as (R / (R + h))^2 and turns with the local vertical over a round Earth.
    # (The stdlib `GravitySpatial` is a uniform field with a constant mass.) `scale = 0` switches
    # gravity off for the vacuum check.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z) in the launch frame"]
        m::Real, [unit = "kg", description = "Current mass"]
    end
    @parameters begin
        mu::Real = 3.986004418e14, [unit = "m^3/s^2", description = "Gravitational parameter"]
        R::Real = 6378165.0, [unit = "m", description = "Earth radius (centre at (0, 0, -R))"]
        scale::Real = 1.0, [min = 0, description = "Multiplier (0: no gravity)"]
    end
    @variables begin
        s::Real, [description = "Squared quaternion norm"]
        rc::Vec{3}, [unit = "m", description = "CoM from the Earth's centre"]
        r::Real, [unit = "m"]
        Fw::Vec{3}, [unit = "N", description = "Gravity force, world frame"]
        gl::Real, [unit = "m/s^2", description = "Local gravity"]
    end
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
        rc[1] ~ g[5]
        rc[2] ~ g[6]
        rc[3] ~ g[7] + R
        r ~ sqrt(rc[1] * rc[1] + rc[2] * rc[2] + rc[3] * rc[3])
        gl ~ scale * mu / (r * r)
        for k in 1:3
            Fw[k] ~ -m * gl * rc[k] / r
        end
        # F_body = R^T F_world (columns of R are the body axes in the world)
        fx ~ ((g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) * Fw[1] + 2 * (g[2] * g[3] + g[1] * g[4]) * Fw[2] + 2 * (g[2] * g[4] - g[1] * g[3]) * Fw[3]) / s
        fy ~ (2 * (g[2] * g[3] - g[1] * g[4]) * Fw[1] + (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) * Fw[2] + 2 * (g[3] * g[4] + g[1] * g[2]) * Fw[3]) / s
        fz ~ (2 * (g[2] * g[4] + g[1] * g[3]) * Fw[1] + 2 * (g[3] * g[4] - g[1] * g[2]) * Fw[2] + (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) * Fw[3]) / s
        tx ~ 0.0
        ty ~ 0.0
        tz ~ 0.0
    end
end
