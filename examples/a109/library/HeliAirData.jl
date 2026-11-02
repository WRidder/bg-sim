@block HeliAirData begin
    # Air data and attitude of the A109 airframe (a sensor tap: it computes, it adds no physics).
    #
    # The rigid body (`stdlib:spatial/RigidBody3D`) sits on its principal axes P, which are the
    # geometric body axes B (x forward, y left, z up) pitched by `eps` about y, because the
    # report's inertia has a product Ixz. `gP` and `VP` are the pose and twist of P; this block
    # turns them into the geometric frame (`gB`, the pose the 3D scene shows) and then into the
    # report's conventions: body axes x forward, y right, z down (FRD), Euler angles of a
    # north-east-down world. The world of the model is x north, y west, z up, and z = 0 is the
    # ground (sea level unless h_field says otherwise).
    #
    #   u, v, w        air-relative body velocities (FRD, m/s); ui, vi, wi the inertial ones
    #   p, q, r        body rates in FRD axes (rad/s), also in deg/s
    #   phi, theta, psi  roll, pitch, heading (rad and deg)
    #   h, hgt         altitude of the CG and height of the rotor hub above the ground (m)
    #   rho            ISA troposphere density at h + h_field: rho0 (1 - 2.25577e-5 h)^4.25588
    #   vt, beta       airspeed (m/s) and sideslip (deg); kts the airspeed in knots
    #   hdot           rate of climb (m/s); gs the ground speed (m/s)
    #   wn, we, wd     wind (m/s, north-east-down)
    @inputs begin
        gP::Vec{7}, [description = "Pose of the principal frame (qw, qx, qy, qz, x, y, z)"]
        VP::Vec{6}, [description = "Twist of the principal frame [w; v] (RigidBody3D.V)"]
        wn::Real, [description = "Wind towards north (m/s)"]
        we::Real, [description = "Wind towards east (m/s)"]
        wd::Real, [description = "Wind downwards (m/s)"]
    end
    @outputs begin
        gB::Vec{7}
        u::Real
        v::Real
        w::Real
        p::Real
        q::Real
        r::Real
        p_deg::Real
        q_deg::Real
        r_deg::Real
        ui::Real
        vi::Real
        wi::Real
        hdot::Real
        phi::Real
        theta::Real
        psi::Real
        phi_deg::Real
        theta_deg::Real
        psi_deg::Real
        h::Real
        hgt::Real
        rho::Real
        vt::Real
        kts::Real
        beta_deg::Real
        gs::Real
        x::Real
        y::Real
    end
    @parameters begin
        eps::Real = 0.0, [description = "Pitch of the principal x axis above the body x axis about y (rad)"]
        rho0::Real = 1.2250554, [description = "Sea-level density, 2.377e-3 slug/ft^3 (kg/m^3)"]
        h_field::Real = 0.0, [description = "Elevation of the ground z = 0 above sea level (m)"]
        h_hub::Real = 1.5164, [description = "Hub above the CG (m)"]
    end
    @variables begin
        s::Real = 1.0
        RP::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation of P (to world)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation of B (to world)"]
        ce::Real = 1.0
        se::Real = 0.0
        ch::Real = 1.0
        sh::Real = 0.0
    end
    @equations begin
        s ~ gP[1] * gP[1] + gP[2] * gP[2] + gP[3] * gP[3] + gP[4] * gP[4]
        RP[1, 1] ~ (gP[1] * gP[1] + gP[2] * gP[2] - gP[3] * gP[3] - gP[4] * gP[4]) / s
        RP[1, 2] ~ 2 * (gP[2] * gP[3] - gP[1] * gP[4]) / s
        RP[1, 3] ~ 2 * (gP[2] * gP[4] + gP[1] * gP[3]) / s
        RP[2, 1] ~ 2 * (gP[2] * gP[3] + gP[1] * gP[4]) / s
        RP[2, 2] ~ (gP[1] * gP[1] - gP[2] * gP[2] + gP[3] * gP[3] - gP[4] * gP[4]) / s
        RP[2, 3] ~ 2 * (gP[3] * gP[4] - gP[1] * gP[2]) / s
        RP[3, 1] ~ 2 * (gP[2] * gP[4] - gP[1] * gP[3]) / s
        RP[3, 2] ~ 2 * (gP[3] * gP[4] + gP[1] * gP[2]) / s
        RP[3, 3] ~ (gP[1] * gP[1] - gP[2] * gP[2] - gP[3] * gP[3] + gP[4] * gP[4]) / s
        ce ~ cos(eps)
        se ~ sin(eps)
        ch ~ cos(0.5 * eps)
        sh ~ sin(0.5 * eps)
        # R_WB = R_WP R_BP^T with R_BP the rotation by eps about y.
        for k in 1:3
            R[k, 1] ~ RP[k, 1] * ce + RP[k, 3] * se
            R[k, 2] ~ RP[k, 2]
            R[k, 3] ~ RP[k, 3] * ce - RP[k, 1] * se
        end
        # q_WB = q_WP (x) conj(q_BP), q_BP = (cos(eps/2), 0, sin(eps/2), 0).
        gB[1] ~ gP[1] * ch + gP[3] * sh
        gB[2] ~ gP[2] * ch + gP[4] * sh
        gB[3] ~ gP[3] * ch - gP[1] * sh
        gB[4] ~ gP[4] * ch - gP[2] * sh
        gB[5] ~ gP[5]
        gB[6] ~ gP[6]
        gB[7] ~ gP[7]
        # Twist of B = R_BP twist of P; then FLU -> FRD (y and z change sign).
        ui ~ ce * VP[4] + se * VP[6]
        vi ~ -VP[5]
        wi ~ -(ce * VP[6] - se * VP[4])
        # The wind in body axes: R_WB^T (wn, -we, -wd) in FLU, then FRD.
        u ~ ui - (R[1, 1] * wn - R[2, 1] * we - R[3, 1] * wd)
        v ~ vi + (R[1, 2] * wn - R[2, 2] * we - R[3, 2] * wd)
        w ~ wi + (R[1, 3] * wn - R[2, 3] * we - R[3, 3] * wd)
        hdot ~ R[3, 1] * ui - R[3, 2] * vi - R[3, 3] * wi
        p ~ ce * VP[1] + se * VP[3]
        q ~ -VP[2]
        r ~ -(ce * VP[3] - se * VP[1])
        p_deg ~ p * 57.29577951308232
        q_deg ~ q * 57.29577951308232
        r_deg ~ r * 57.29577951308232
        theta ~ asin(clamp(R[3, 1], -1.0, 1.0))
        phi ~ atan(R[3, 2], R[3, 3])
        psi ~ atan(-R[2, 1], R[1, 1])
        phi_deg ~ phi * 57.29577951308232
        theta_deg ~ theta * 57.29577951308232
        psi_deg ~ psi * 57.29577951308232
        h ~ gP[7]
        hgt ~ gP[7] + h_hub
        x ~ gP[5]
        y ~ gP[6]
        rho ~ rho0 * (1.0 - 2.25577e-5 * (h + h_field))^4.25588
        vt ~ sqrt(u * u + v * v + w * w)
        kts ~ vt / 0.5144444444444445
        beta_deg ~ atan(v, sqrt(u * u + w * w)) * 57.29577951308232
        gs ~ sqrt(ui * ui + vi * vi + wi * wi)
    end
end
