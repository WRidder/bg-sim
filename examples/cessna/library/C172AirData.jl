@block C172AirData begin
    # Air data and attitude of the Cessna 172 (a sensor tap: it computes, it adds no physics).
    #
    # `g` and `V` are the world pose and the body twist [w; v] of the airframe's RigidBody3D,
    # whose frame is the body frame at the centre of gravity: x forward, y left, z up (FLU; the
    # small products of inertia are neglected, so the principal axes are the body axes). The
    # world is x north, y west, z up. The outputs follow JSBSim's c172p conventions: body axes
    # x forward, y right, z down (FRD) and the Euler angles of a north-east-down world.
    #
    #   u, v, w        air-relative body velocity (FRD, m/s): the inertial velocity minus the wind
    #   p, q, r        body rates (FRD, rad/s)
    #   vt, qbar       true airspeed and dynamic pressure; mach, cas (calibrated airspeed, m/s)
    #   alpha, beta    regularised as in c172_ref.py: alpha = atan(w / sqrt(u^2 + vf^2)),
    #                  beta = atan(v / sqrt(u^2 + w^2 + vf^2)) (vf = 1 m/s keeps both finite at rest)
    #   bi2v, ci2v     b/(2 V) and cbar/(2 V) with V = sqrt(vt^2 + vf^2)
    #   hb             height of the aerodynamic reference point above the runway over the span
    #                  (the ground-effect tables' argument)
    #   pa, T, rho, a  ISA troposphere (JSBSim's standard atmosphere below 11 km)
    #   p_tot          total (pitot) pressure pa (1 + 0.2 M^2)^3.5, the engine's ram-air pressure
    @inputs begin
        g::Vec{7}, [description = "World pose of the airframe (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Body twist [w; v] (RigidBody3D.V), FLU"]
        wn::Real, [unit = "m/s", description = "Wind towards north"]
        we::Real, [unit = "m/s", description = "Wind towards east"]
        wd::Real, [unit = "m/s", description = "Wind downwards"]
    end
    @outputs begin
        u::Real, [unit = "m/s"]
        v::Real, [unit = "m/s"]
        w::Real, [unit = "m/s"]
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        vt::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
        beta::Real, [unit = "rad"]
        alpha_deg::Real
        beta_deg::Real
        bi2v::Real, [unit = "s"]
        ci2v::Real, [unit = "s"]
        qbar::Real, [unit = "Pa"]
        mach::Real
        cas::Real, [unit = "m/s"]
        pa::Real, [unit = "Pa"]
        p_tot::Real, [unit = "Pa"]
        T::Real, [unit = "K"]
        rho::Real, [unit = "kg/m^3"]
        a::Real, [unit = "m/s"]
        h::Real, [unit = "m"]
        hb::Real
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        gamma::Real, [unit = "rad"]
        hdot::Real, [unit = "m/s"]
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
        gs::Real, [unit = "m/s", description = "Ground speed"]
    end
    @parameters begin
        vf::Real = 1.0, [unit = "m/s", min = 1.0e-6, description = "Regularisation speed of alpha, beta and b/(2V)"]
        b::Real = 10.91184, [unit = "m", description = "Wing span (35.8 ft)"]
        cbar::Real = 1.49352, [unit = "m", description = "Mean aerodynamic chord (4.9 ft)"]
        rax::Real = 0.0, [unit = "m", description = "Aerodynamic reference point, body x"]
        ray::Real = 0.0, [unit = "m", description = "Aerodynamic reference point, body y"]
        raz::Real = 0.0, [unit = "m", description = "Aerodynamic reference point, body z"]
        ground_z::Real = 0.0, [unit = "m", description = "Runway height (world z)"]
        T0::Real = 288.15, [unit = "K", description = "Sea-level temperature"]
        p0::Real = 101325.0, [unit = "Pa", description = "Sea-level pressure"]
        lapse::Real = 0.0065, [unit = "K/m", description = "Temperature lapse rate"]
        Rgas::Real = 287.0531, [unit = "J/(kg*K)", description = "Gas constant of air (JSBSim)"]
        g0::Real = 9.80665, [unit = "m/s^2", description = "Standard gravity"]
    end
    @variables begin
        s::Real = 1.0
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation body -> world"]
        ui::Real = 0.0, [unit = "m/s", description = "Inertial body velocity x (FRD)"]
        vi::Real = 0.0, [unit = "m/s", description = "Inertial body velocity y (FRD)"]
        wi::Real = 0.0, [unit = "m/s", description = "Inertial body velocity z (FRD)"]
        vs::Real = 1.0, [unit = "m/s", description = "sqrt(vt^2 + vf^2)"]
        a0::Real = 340.294, [unit = "m/s", description = "Sea-level speed of sound"]
        qc::Real = 0.0, [unit = "Pa", description = "Impact pressure p_tot - pa"]
        vn::Real = 0.0, [unit = "m/s", description = "Velocity north"]
        vw::Real = 0.0, [unit = "m/s", description = "Velocity west"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        # FLU -> FRD: y and z change sign.
        ui ~ V[4]
        vi ~ -V[5]
        wi ~ -V[6]
        p ~ V[1]
        q ~ -V[2]
        r ~ -V[3]
        # The wind in body axes: R^T (wn, -we, -wd) in FLU, then FRD.
        u ~ ui - (R[1, 1] * wn - R[2, 1] * we - R[3, 1] * wd)
        v ~ vi + (R[1, 2] * wn - R[2, 2] * we - R[3, 2] * wd)
        w ~ wi + (R[1, 3] * wn - R[2, 3] * we - R[3, 3] * wd)
        vt ~ sqrt(u * u + v * v + w * w)
        alpha ~ atan(w / sqrt(u * u + vf * vf))
        beta ~ atan(v / sqrt(u * u + w * w + vf * vf))
        alpha_deg ~ alpha * 57.29577951308232
        beta_deg ~ beta * 57.29577951308232
        vs ~ sqrt(vt * vt + vf * vf)
        bi2v ~ b / (2.0 * vs)
        ci2v ~ cbar / (2.0 * vs)
        h ~ g[7]
        x ~ g[5]
        y ~ g[6]
        T ~ T0 - lapse * h
        pa ~ p0 * (T / T0)^(g0 / (lapse * Rgas))
        rho ~ pa / (Rgas * T)
        a ~ sqrt(1.4 * Rgas * T)
        a0 ~ sqrt(1.4 * Rgas * T0)
        qbar ~ 0.5 * rho * vt * vt
        mach ~ vt / a
        p_tot ~ pa * (1.0 + 0.2 * mach * mach)^3.5
        qc ~ p_tot - pa
        cas ~ a0 * sqrt(5.0 * ((qc / p0 + 1.0)^(2.0 / 7.0) - 1.0))
        hb ~ (h - ground_z + R[3, 1] * rax + R[3, 2] * ray + R[3, 3] * raz) / b
        # NED Euler angles from R (world x north, y west, z up; body FLU).
        theta ~ asin(clamp(R[3, 1], -1.0, 1.0))
        phi ~ atan(R[3, 2], R[3, 3])
        psi ~ atan(-R[2, 1], R[1, 1])
        hdot ~ R[3, 1] * ui - R[3, 2] * vi - R[3, 3] * wi
        gamma ~ asin(clamp((R[3, 1] * u - R[3, 2] * v - R[3, 3] * w) / vs, -1.0, 1.0))
        vn ~ R[1, 1] * ui - R[1, 2] * vi - R[1, 3] * wi
        vw ~ R[2, 1] * ui - R[2, 2] * vi - R[2, 3] * wi
        gs ~ sqrt(vn * vn + vw * vw)
    end
end
