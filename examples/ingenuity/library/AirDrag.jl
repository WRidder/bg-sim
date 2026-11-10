@block AirDrag begin
    # Air data and blunt-body drag of the airframe (fuselage, mast, solar panel and legs), the
    # HeliCAT fuselage model of Grip et al. (2017): a drag area with no angle-of-attack
    # dependency. From the pose chart (qw qx qy qz x y z) and the body twist [w; v] of the
    # `RigidBody3D` it gives the airframe's velocity relative to the air in the body frame,
    #
    #     va = v - R^T wind,
    #
    # (what the rotors' inflow sees) and the drag force -1/2 rho CdA |va| va, applied at the
    # fuselage centre through an `ExternalWrenchSpatial` (the outputs fx, fy, fz; no moment about the
    # mount point). |va| is smoothed by `veps` so the law has no kink at rest.
    @inputs begin
        pose::Vec{7}
        V::Vec{6}
    end
    @outputs begin
        va::Vec{3}
        wb::Vec{3}
        airspeed::Real, [unit = "m/s"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @parameters begin
        rho::Real = 0.0165, [unit = "kg/m^3", min = 0.005, max = 0.03, description = "Air density"]
        wind::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Wind velocity, world frame (x east, y north, z up)"]
        CdA::Real = 0.065, [unit = "m^2", min = 0, description = "Airframe drag area D/q"]
        veps::Real = 0.01, [unit = "m/s", min = 1.0e-6, description = "Smoothing speed of |va|"]
    end
    @variables begin
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        sp::Real = 0.01, [unit = "m/s", description = "Smoothed airspeed"]
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
        va[1] ~ V[4] - (R[1, 1] * wind[1] + R[2, 1] * wind[2] + R[3, 1] * wind[3])
        va[2] ~ V[5] - (R[1, 2] * wind[1] + R[2, 2] * wind[2] + R[3, 2] * wind[3])
        va[3] ~ V[6] - (R[1, 3] * wind[1] + R[2, 3] * wind[2] + R[3, 3] * wind[3])
        wb[1] ~ V[1]
        wb[2] ~ V[2]
        wb[3] ~ V[3]
        sp ~ sqrt(va[1] * va[1] + va[2] * va[2] + va[3] * va[3] + veps * veps)
        airspeed ~ sp
        fx ~ -0.5 * rho * CdA * sp * va[1]
        fy ~ -0.5 * rho * CdA * sp * va[2]
        fz ~ -0.5 * rho * CdA * sp * va[3]
    end
end
