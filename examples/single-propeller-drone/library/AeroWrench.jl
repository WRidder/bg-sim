@block AeroWrench begin
    # External aerodynamic wrench on the airframe, in the body frame about the centre of mass,
    # as the six scalar inputs of `stdlib:multibond/ExternalWrenchSpatial`. These loads are
    # imposed wrenches (signals into a wrench source), not bonds: the air is not modelled.
    #
    #   thrust     T along body +z (the rotor line passes through the CoM, so no moment)
    #   hub moment Mx, My from the rotor (`PropRotor`: the swashplateless moment)
    #   rotor disc drag   -q A_d C_dd |u_xy| u_xy at z_d (the rotor H-force, above the CoM)
    #   body drag         -q A_b C_db |u| u at z_b (the body tube)
    #   contact normal    the landing-gear force, for the accelerometer only (the contacts are
    #                     bonded to the body themselves)
    #
    # `u = v_b - R^T wind` is the air-relative velocity in body axes; `wind` is a steady world
    # wind (a parameter). The two drag forces act above and below the CoM, so a horizontal
    # flight speed gives a pitch/roll moment growing with u^2 that the attitude loop holds; it
    # has nothing to do with the heading. The motor reaction and the rotor gyroscopic torque are
    # NOT here: they arrive through the `PropRotor` spatial bond. The fin loads are `FinSet`'s.
    # `fs` is the specific force of these loads plus the contact normal (never gravity); the
    # accelerometer adds the fins' share (`AddVec3`).
    #
    # `fc_max` is a peak hold of the landing-gear force: d/dt fc_max = k_pk max(fc - fc_max, 0),
    # smoothed over 1e-5 N, which follows a rising force within 1/k_pk and then holds the
    # largest value, so the touchdown load is read exactly although the impact lasts a few
    # milliseconds and the output grid is coarser. The touchdown detection of the drive and of
    # the mission reads it, so an impact between two of their ticks is not missed. It starts at
    # 1 N, so it is idle (no stiffness) while the feet are off the ground; the smoothing lets it
    # creep by k_pk 2.5e-11/fc_max N/s, 5e-7 N/s at 1 N, far from the 2 N touchdown threshold.
    @inputs begin
        T::Real, [unit = "N"]
        Mx::Real, [unit = "N*m"]
        My::Real, [unit = "N*m"]
        V::Vec{6}
        pose::Vec{7}
        leg::Vec{4}
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        fs::Vec{3}
        Fdrag::Real, [unit = "N"]
        fc::Real, [unit = "N", description = "Total landing-gear normal force (world z)"]
        fc_max::Real, [unit = "N", description = "Largest landing-gear force so far (peak hold)"]
    end
    @parameters begin
        m::Real = 1.2, [unit = "kg", min = 0.01, description = "Total mass (for the specific force)"]
        rho::Real = 1.225, [unit = "kg/m^3", min = 0, description = "Air density"]
        wind::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Steady wind, world frame"]
        Adisc::Real = 0.073, [unit = "m^2", min = 0, description = "Rotor disc area"]
        Cdd::Real = 0.5, [min = 0, description = "Drag coefficient of the rotor disc (H-force)"]
        zd::Real = 0.18, [unit = "m", description = "Rotor disc height above the CoM"]
        Ab::Real = 0.026, [unit = "m^2", min = 0, description = "Frontal area of the body tube"]
        Cdb::Real = 1.0, [min = 0, description = "Drag coefficient of the body"]
        zb::Real = -0.01, [unit = "m", description = "Body drag centre relative to the CoM"]
        clin::Real = 0.08, [unit = "N*s/m", min = 0, description = "Linear drag for numerical smoothness"]
        epsv::Real = 1.0e-3, [unit = "m/s", min = 1.0e-9, description = "Smoothing speed of |u| u"]
        onel::Vec{4} = [1.0, 1.0, 1.0, 1.0], [description = "Summation vector over the contacts"]
        k_pk::Real = 2.0e4, [unit = "1/s", min = 0, description = "Tracking rate of the peak hold"]
    end
    @variables begin
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        s::Real = 1.0, [description = "Squared quaternion norm"]
        ux::Real = 0.0, [unit = "m/s", description = "Air-relative velocity, body x"]
        uy::Real = 0.0, [unit = "m/s", description = "Air-relative velocity, body y"]
        uz::Real = 0.0, [unit = "m/s", description = "Air-relative velocity, body z"]
        axy::Real = 0.0, [unit = "m/s", description = "Smooth horizontal air speed"]
        a3::Real = 0.0, [unit = "m/s", description = "Smooth total air speed"]
        fdx::Real = 0.0, [unit = "N", description = "Rotor disc drag, body x"]
        fdy::Real = 0.0, [unit = "N", description = "Rotor disc drag, body y"]
        fbx::Real = 0.0, [unit = "N", description = "Body drag, body x"]
        fby::Real = 0.0, [unit = "N", description = "Body drag, body y"]
        fbz::Real = 0.0, [unit = "N", description = "Body drag, body z"]
        fcs::Real = 0.0, [unit = "N", description = "Total contact normal force (world z)"]
        fpk::Real = 1.0, [unit = "N", state = :prefer, description = "Peak-hold state"]
    end
    @equations begin
        s ~ pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        R[1, 1] ~ (pose[1] * pose[1] + pose[2] * pose[2] - pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[1, 2] ~ 2 * (pose[2] * pose[3] - pose[1] * pose[4]) / s
        R[1, 3] ~ 2 * (pose[2] * pose[4] + pose[1] * pose[3]) / s
        R[2, 1] ~ 2 * (pose[2] * pose[3] + pose[1] * pose[4]) / s
        R[2, 2] ~ (pose[1] * pose[1] - pose[2] * pose[2] + pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[2, 3] ~ 2 * (pose[3] * pose[4] - pose[1] * pose[2]) / s
        R[3, 1] ~ 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s
        R[3, 2] ~ 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s
        R[3, 3] ~ (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s
        ux ~ V[4] - (R[1, 1] * wind[1] + R[2, 1] * wind[2] + R[3, 1] * wind[3])
        uy ~ V[5] - (R[1, 2] * wind[1] + R[2, 2] * wind[2] + R[3, 2] * wind[3])
        uz ~ V[6] - (R[1, 3] * wind[1] + R[2, 3] * wind[2] + R[3, 3] * wind[3])
        axy ~ sqrt(ux * ux + uy * uy + epsv * epsv)
        a3 ~ sqrt(ux * ux + uy * uy + uz * uz + epsv * epsv)
        fdx ~ -0.5 * rho * Adisc * Cdd * axy * ux - clin * ux
        fdy ~ -0.5 * rho * Adisc * Cdd * axy * uy - clin * uy
        fbx ~ -0.5 * rho * Ab * Cdb * a3 * ux
        fby ~ -0.5 * rho * Ab * Cdb * a3 * uy
        fbz ~ -0.5 * rho * Ab * Cdb * a3 * uz
        fcs ~ dot(leg, onel)
        fc ~ fcs
        ddt(fpk) ~ 0.5 * k_pk * ((fcs - fpk) + sqrt((fcs - fpk) * (fcs - fpk) + 1.0e-10))
        fc_max ~ fpk
        fx ~ fdx + fbx
        fy ~ fdy + fby
        fz ~ T + fbz
        tx ~ Mx - zd * fdy - zb * fby
        ty ~ My + zd * fdx + zb * fbx
        tz ~ 0.0
        Fdrag ~ sqrt((fdx + fbx) * (fdx + fbx) + (fdy + fby) * (fdy + fby) + fbz * fbz)
        fs[1] ~ fx / m + R[3, 1] * fcs / m
        fs[2] ~ fy / m + R[3, 2] * fcs / m
        fs[3] ~ fz / m + R[3, 3] * fcs / m
    end
end
