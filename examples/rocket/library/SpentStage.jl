@block SpentStage begin
    # Where a jettisoned part is, for the 3D view (a tap: it does not act on the vehicle; the
    # vehicle's own mass drop is `FlightSequence`'s jettison). Until `t_sep` the part rides on the
    # vehicle: its pose is the vehicle's attitude at the view origin (`RocketView.gv`; the part's
    # visuals sit at their place in the stack inside its link). At `t_sep` an event copies the
    # vehicle's position, attitude and velocity, less `dv_sep` along the vehicle axis (retro
    # rockets, separation springs), and from then on the part flies ballistically under
    # inverse-square gravity, without drag and without turning. The output pose is relative to
    # the vehicle, as the view keeps the vehicle at the origin.
    @inputs begin
        g::Vec{7}, [description = "Vehicle pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Vehicle twist [w; v] in body axes"]
    end
    @parameters begin
        t_sep::Real = 1.0e9, [unit = "s", description = "Separation time"]
        dv_sep::Real = 5.0, [unit = "m/s", description = "Separation speed backwards along the vehicle axis"]
        mu::Real = 3.986004418e14, [unit = "m^3/s^2", description = "Gravitational parameter"]
        R::Real = 6378165.0, [unit = "m", description = "Earth radius"]
    end
    @variables begin
        x::Real = 0.0, [unit = "m", description = "Position x (launch frame)"]
        y::Real = 0.0, [unit = "m"]
        z::Real = 0.0, [unit = "m"]
        vx::Real = 0.0, [unit = "m/s"]
        vy::Real = 0.0, [unit = "m/s"]
        vz::Real = 0.0, [unit = "m/s"]
        qw::Real = 1.0
        qx::Real = 0.0
        qy::Real = 0.0
        qz::Real = 0.0
        free::Real, [description = "1 after the separation"]
        r3::Real, [unit = "m^3"]
        s2::Real
    end
    @outputs begin
        pose::Vec{7}
        dist::Real, [unit = "m", description = "Distance from the vehicle"]
    end
    @equations begin
        free ~ ifelse(t >= t_sep, 1.0, 0.0)
        r3 ~ sqrt(x * x + y * y + (z + R) * (z + R)) * (x * x + y * y + (z + R) * (z + R))
        ddt(x) ~ free * vx
        ddt(y) ~ free * vy
        ddt(z) ~ free * vz
        ddt(vx) ~ -free * mu * x / r3
        ddt(vy) ~ -free * mu * y / r3
        ddt(vz) ~ -free * mu * (z + R) / r3
        ddt(qw) ~ 0.0
        ddt(qx) ~ 0.0
        ddt(qy) ~ 0.0
        ddt(qz) ~ 0.0
        s2 ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        pose[1] ~ ifelse(t >= t_sep, qw, g[1])
        pose[2] ~ ifelse(t >= t_sep, qx, g[2])
        pose[3] ~ ifelse(t >= t_sep, qy, g[3])
        pose[4] ~ ifelse(t >= t_sep, qz, g[4])
        pose[5] ~ free * (x - g[5])
        pose[6] ~ free * (y - g[6])
        pose[7] ~ free * (z - g[7])
        dist ~ sqrt(pose[5] * pose[5] + pose[6] * pose[6] + pose[7] * pose[7])
    end
    @events begin
        t > t_sep => begin
            reinit(x, g[5])
            reinit(y, g[6])
            reinit(z, g[7])
            # world velocity R(q) (V[4:6] - dv_sep e_x)
            reinit(vx, ((g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) * (V[4] - dv_sep) + 2 * (g[2] * g[3] - g[1] * g[4]) * V[5] + 2 * (g[2] * g[4] + g[1] * g[3]) * V[6]) / s2)
            reinit(vy, (2 * (g[2] * g[3] + g[1] * g[4]) * (V[4] - dv_sep) + (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) * V[5] + 2 * (g[3] * g[4] - g[1] * g[2]) * V[6]) / s2)
            reinit(vz, (2 * (g[2] * g[4] - g[1] * g[3]) * (V[4] - dv_sep) + 2 * (g[3] * g[4] + g[1] * g[2]) * V[5] + (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) * V[6]) / s2)
            reinit(qw, g[1])
            reinit(qx, g[2])
            reinit(qy, g[3])
            reinit(qz, g[4])
        end
    end
end
