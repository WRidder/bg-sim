@block MissileAirData begin
    # Air data and attitude of the missile (a sensor tap: it computes, it adds no physics).
    #
    # Body axes are x forward, y left, z up (the FLU frame of `RigidBody3D`). The aerodynamic
    # angles are the usual ones:
    #
    #   alpha = atan(-w, u)     positive nose up (the air comes from below)
    #   beta  = atan(-v, sqrt(u^2 + w^2))   positive nose left
    #
    # `q_up` and `r_right` turn the FLU body rates into the aviation sense the control laws and
    # the plots use: positive pitch rate is nose up, positive yaw rate is nose right. `gz_body`
    # is the world z axis in body axes (1 in level flight), the gravity component of the
    # acceleration command.
    #
    # Below `vf` the speed is floored and alpha/beta are 0: neither sqrt nor atan2 has a
    # derivative at rest, which the solver's Jacobian needs.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
        rho::Real, [unit = "kg/m^3", description = "Air density"]
        a::Real, [unit = "m/s", description = "Speed of sound"]
    end
    @parameters vf::Real = 1.0, [unit = "m/s", min = 1.0e-6, description = "Speed floor for the directions at rest"]
    @variables begin
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        v2::Real = 0.0, [unit = "m^2/s^2", description = "Squared airspeed"]
        vmag::Real = 0.0, [unit = "m/s"]
    end
    @outputs begin
        va::Vec{3}, [unit = "m/s", description = "Air-relative velocity in body axes"]
        vw::Vec{3}, [unit = "m/s", description = "Inertial velocity in world axes"]
        vt::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
        beta::Real, [unit = "rad"]
        alpha_deg::Real
        beta_deg::Real
        qbar::Real, [unit = "Pa"]
        mach::Real
        h::Real, [unit = "m"]
        hdot::Real, [unit = "m/s"]
        p::Real, [unit = "rad/s"]
        q_up::Real, [unit = "rad/s", description = "Pitch rate, positive nose up"]
        r_right::Real, [unit = "rad/s", description = "Yaw rate, positive nose right"]
        p_deg::Real
        q_deg::Real
        r_deg::Real
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        gamma::Real, [unit = "rad"]
        theta_deg::Real
        phi_deg::Real
        psi_deg::Real
        gamma_deg::Real
        gz_body::Real, [description = "World z (up) in body axes, R[3,3]"]
        pos::Vec{3}, [unit = "m", description = "Position in world axes"]
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
        z::Real, [unit = "m"]
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
        va[1] ~ V[4]
        va[2] ~ V[5]
        va[3] ~ V[6]
        v2 ~ va[1] * va[1] + va[2] * va[2] + va[3] * va[3]
        vmag ~ sqrt(v2 + vf * vf)
        vt ~ vmag
        alpha ~ ifelse(v2 > vf * vf, atan(-va[3] / vmag, va[1] / vmag), 0.0)
        beta ~ ifelse(v2 > vf * vf, atan(-va[2] / vmag, sqrt(va[1] * va[1] + va[3] * va[3]) / vmag), 0.0)
        alpha_deg ~ alpha * 180.0 / pi
        beta_deg ~ beta * 180.0 / pi
        qbar ~ 0.5 * rho * v2
        mach ~ vmag / max(a, 1.0e-6)
        h ~ g[7]
        for k in 1:3
            vw[k] ~ R[k, 1] * V[4] + R[k, 2] * V[5] + R[k, 3] * V[6]
        end
        hdot ~ vw[3]
        p ~ V[1]
        q_up ~ -V[2]
        r_right ~ -V[3]
        p_deg ~ V[1] * 57.29577951308232
        q_deg ~ -V[2] * 57.29577951308232
        r_deg ~ -V[3] * 57.29577951308232
        phi ~ atan(R[3, 2], R[3, 3])
        theta ~ atan(-R[3, 1], hypot(R[3, 2], R[3, 3]))
        psi ~ atan(R[2, 1], R[1, 1])
        gamma ~ asin(clamp(vw[3] / sqrt(vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3] + vf * vf), -1.0, 1.0))
        theta_deg ~ theta * 180.0 / pi
        phi_deg ~ phi * 180.0 / pi
        psi_deg ~ psi * 180.0 / pi
        gamma_deg ~ gamma * 180.0 / pi
        gz_body ~ R[3, 3]
        pos[1] ~ g[5]
        pos[2] ~ g[6]
        pos[3] ~ g[7]
        x ~ g[5]
        y ~ g[6]
        z ~ g[7]
    end
end
