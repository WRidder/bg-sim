@block BeaverAirData begin
    # Air data and attitude of the Beaver airframe (a sensor tap: it computes, it adds no physics).
    #
    # The rigid body (`stdlib:spatial/RigidBody3D`) sits on its principal axes P: the geometric body
    # axes B (x forward, y left, z up) pitched by `eps` about y, because the inertia has a product
    # Jxz. `gP` and `VP` are the pose and twist of P; this block turns them into the geometric frame
    # (`gB`, the pose the 3D scene shows) and into the conventions of the FDC 'Beaver' model (Rauw):
    # body axes x forward, y right, z down (FRD), Euler angles of a north-east-down world. The world
    # of the model is x north, y west, z up.
    #
    #   V, alpha, beta     true airspeed (m/s), angle of attack and sideslip (rad), relative to the air
    #   p, q, r            body rates in FRD axes (rad/s)
    #   phi, theta, psi    roll, pitch, heading (rad); gamma the flight-path angle; phidot the exact
    #                      Euler rate p + tan(theta)(q sin(phi) + r cos(phi)) (for a growth rate)
    #   H, north, east     altitude and ground position (m); hdot the climb rate
    #   rho, ps, T, g      the FDC atmosphere (fdclib1.mdl): T = 288.15 - 0.0065 H,
    #                      g = 9.80665 (6371020/(6371020 + H))^2, ps = 101325 (T/288.15)^(g/1.86584),
    #                      rho = ps/(287.053 T)
    #   qd, mach, vc       dynamic pressure (Pa), Mach number and calibrated airspeed (m/s), FDC airdata:
    #                      a = sqrt(401.8743 T), qc = ps((1 + 0.2 M^2)^3.5 - 1),
    #                      Vc = sqrt(579000 ((1 + qc/101325)^(1/3.5) - 1))
    #   wn, we, wd         wind (m/s, north-east-down): V, alpha, beta are relative to the air,
    #                      ui, vi, wi the inertial body velocity (FRD)
    @inputs begin
        gP::Vec{7}, [description = "Pose of the principal frame (qw, qx, qy, qz, x, y, z)"]
        VP::Vec{6}, [description = "Twist of the principal frame [w; v] (RigidBody3D.V)"]
        wn::Real, [unit = "m/s", description = "Wind towards north"]
        we::Real, [unit = "m/s", description = "Wind towards east"]
        wd::Real, [unit = "m/s", description = "Wind downwards"]
    end
    @outputs begin
        gB::Vec{7}
        V::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
        beta::Real, [unit = "rad"]
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        gamma::Real, [unit = "rad"]
        phidot::Real, [unit = "rad/s"]
        H::Real, [unit = "m"]
        north::Real, [unit = "m"]
        east::Real, [unit = "m"]
        hdot::Real, [unit = "m/s"]
        ui::Real, [unit = "m/s"]
        vi::Real, [unit = "m/s"]
        wi::Real, [unit = "m/s"]
        rho::Real
        ps::Real
        T::Real
        g::Real
        qd::Real, [unit = "Pa"]
        mach::Real
        vc::Real
        alpha_deg::Real
        beta_deg::Real
        p_deg::Real
        q_deg::Real
        r_deg::Real
        phi_deg::Real
        theta_deg::Real
        psi_deg::Real
        gamma_deg::Real
    end
    @parameters begin
        eps::Real = 0.0, [description = "Pitch of the principal x axis above the body x axis about y (rad)"]
    end
    @variables begin
        s::Real = 1.0
        RP::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation of P (to world)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation of B (to world)"]
        ce::Real = 1.0
        se::Real = 0.0
        ch::Real = 1.0
        sh::Real = 0.0
        ub::Real = 0.0, [description = "Air-relative body velocity x (forward), m/s"]
        vb::Real = 0.0, [description = "Air-relative body velocity y (right), m/s"]
        wb::Real = 0.0, [description = "Air-relative body velocity z (down), m/s"]
        qc::Real = 0.0, [description = "Impact pressure"]
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
        # The wind in body axes: R_WB^T (wn, -we, -wd) in FLU (the world is x north, y west, z up), then FRD.
        ub ~ ui - (R[1, 1] * wn - R[2, 1] * we - R[3, 1] * wd)
        vb ~ vi + (R[1, 2] * wn - R[2, 2] * we - R[3, 2] * wd)
        wb ~ wi + (R[1, 3] * wn - R[2, 3] * we - R[3, 3] * wd)
        hdot ~ R[3, 1] * ui - R[3, 2] * vi - R[3, 3] * wi
        p ~ ce * VP[1] + se * VP[3]
        q ~ -VP[2]
        r ~ -(ce * VP[3] - se * VP[1])
        V ~ sqrt(ub * ub + vb * vb + wb * wb)
        alpha ~ atan(wb, ub)
        beta ~ asin(vb / V)
        # Euler angles of the north-east-down convention from R_WB (world x north, y west, z up).
        theta ~ asin(clamp(R[3, 1], -1.0, 1.0))
        phi ~ atan(R[3, 2], R[3, 3])
        psi ~ atan(-R[2, 1], R[1, 1])
        gamma ~ asin(clamp((R[3, 1] * ub - R[3, 2] * vb - R[3, 3] * wb) / V, -1.0, 1.0))
        phidot ~ p + tan(theta) * (q * sin(phi) + r * cos(phi))
        H ~ gP[7]
        north ~ gP[5]
        east ~ -gP[6]
        # FDC atmosphere and air data
        T ~ 288.15 - 0.0065 * H
        g ~ 9.80665 * (6371020.0 / (6371020.0 + H))^2
        ps ~ 101325.0 * (T / 288.15)^(g / 1.86584)
        rho ~ ps / (287.053 * T)
        qd ~ 0.5 * rho * V * V
        mach ~ V / sqrt(401.8743 * T)
        qc ~ ps * ((1.0 + 0.2 * mach * mach)^3.5 - 1.0)
        vc ~ sqrt(579000.0 * ((1.0 + qc / 101325.0)^(1.0 / 3.5) - 1.0))
        alpha_deg ~ alpha * 57.29577951308232
        beta_deg ~ beta * 57.29577951308232
        p_deg ~ p * 57.29577951308232
        q_deg ~ q * 57.29577951308232
        r_deg ~ r * 57.29577951308232
        phi_deg ~ phi * 57.29577951308232
        theta_deg ~ theta * 57.29577951308232
        psi_deg ~ psi * 57.29577951308232
        gamma_deg ~ gamma * 57.29577951308232
    end
end
