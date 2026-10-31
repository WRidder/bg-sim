@block F16AirData begin
    # Air data and attitude of the F-16 airframe (a sensor tap: it computes, it adds no physics).
    #
    # The rigid body (`stdlib:spatial/RigidBody3D`) sits on its principal axes P, which are the
    # geometric body axes B (x forward, y left, z up) pitched by `eps` about y, because the book's
    # inertia has a product Jxz. `gP` and `VP` are the pose and twist of P; this block turns them
    # into the geometric frame (`gB`, the pose the 3D scene shows) and then into the book's
    # conventions: body axes x forward, y right, z down (FRD), Euler angles of a north-east-down
    # world. The world of the model is x north, y west, z up.
    #
    #   vt, alpha, beta    airspeed (m/s), angle of attack and sideslip (rad; also in deg, the unit
    #                      of the NASA tables)
    #   p, q, r            body rates in FRD axes (rad/s; q > 0 is nose up), q_deg in deg/s
    #   phi, theta, psi    roll, pitch, heading (rad), gamma the flight-path angle
    #   h, mach, qbar      altitude (m), Mach number and dynamic pressure (Pa) from the book's
    #                      standard-atmosphere fit (Stevens & Lewis ADC, converted to SI):
    #                      T = 519 R (1 - 0.703e-5 h/ft), 390 R above 35000 ft;
    #                      rho = 2.377e-3 slug/ft^3 (1 - 0.703e-5 h/ft)^4.14
    @inputs begin
        gP::Vec{7}, [description = "Pose of the principal frame (qw, qx, qy, qz, x, y, z)"]
        VP::Vec{6}, [description = "Twist of the principal frame [w; v] (RigidBody3D.V)"]
    end
    @outputs begin
        gB::Vec{7}
        vt::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
        beta::Real, [unit = "rad"]
        alpha_deg::Real
        beta_deg::Real
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        q_deg::Real
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        gamma::Real, [unit = "rad"]
        theta_deg::Real
        h::Real, [unit = "m"]
        mach::Real
        qbar::Real, [unit = "Pa"]
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
    end
    @parameters begin
        eps::Real = 0.0, [description = "Pitch of the principal x axis above the body x axis about y (rad)"]
        rho0::Real = 1.2250554, [description = "Sea-level density, 2.377e-3 slug/ft^3 (kg/m^3)"]
        klapse::Real = 2.3064304e-5, [description = "0.703e-5 per ft, in 1/m"]
        h_trop::Real = 10668.0, [description = "35000 ft: constant temperature above (m)"]
        a_gas::Real = 14.9408595, [description = "sqrt(1.4*1716.3 ft^2/(s^2 R))*0.3048: a = a_gas*sqrt(T/R) in m/s"]
    end
    @variables begin
        s::Real = 1.0
        RP::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation of P (to world)"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rotation of B (to world)"]
        ce::Real = 1.0
        se::Real = 0.0
        ch::Real = 1.0
        sh::Real = 0.0
        ub::Real = 0.0, [description = "Body velocity x (forward), m/s"]
        vb::Real = 0.0, [description = "Body velocity y (right), m/s"]
        wb::Real = 0.0, [description = "Body velocity z (down), m/s"]
        tfac::Real = 1.0
        Tr::Real = 519.0, [description = "Ambient temperature (Rankine, as in the book)"]
        rho::Real = 1.2250554, [description = "Density (kg/m^3)"]
        a::Real = 340.0, [description = "Speed of sound (m/s)"]
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
        ub ~ ce * VP[4] + se * VP[6]
        vb ~ -VP[5]
        wb ~ -(ce * VP[6] - se * VP[4])
        p ~ ce * VP[1] + se * VP[3]
        q ~ -VP[2]
        r ~ -(ce * VP[3] - se * VP[1])
        q_deg ~ q * 57.29577951308232
        vt ~ sqrt(ub * ub + vb * vb + wb * wb)
        alpha ~ atan(wb, ub)
        beta ~ asin(vb / vt)
        alpha_deg ~ alpha * 57.29577951308232
        beta_deg ~ beta * 57.29577951308232
        # Euler angles of the north-east-down convention from R_WB (world x north, y west, z up).
        theta ~ asin(clamp(R[3, 1], -1.0, 1.0))
        phi ~ atan(R[3, 2], R[3, 3])
        psi ~ atan(-R[2, 1], R[1, 1])
        theta_deg ~ theta * 57.29577951308232
        gamma ~ asin(clamp((R[3, 1] * ub - R[3, 2] * vb - R[3, 3] * wb) / vt, -1.0, 1.0))
        h ~ gP[7]
        x ~ gP[5]
        y ~ gP[6]
        tfac ~ 1.0 - klapse * h
        Tr ~ ifelse(h >= h_trop, 390.0, 519.0 * tfac)
        rho ~ rho0 * tfac^4.14
        a ~ a_gas * sqrt(Tr)
        mach ~ vt / a
        qbar ~ 0.5 * rho * vt * vt
    end
end
