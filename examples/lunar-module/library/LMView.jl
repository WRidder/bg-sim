@block LMView begin
    # Poses for the 3D view (a tap: no physics). The view keeps the vehicle at the origin and
    # moves the world, because the vehicle flies hundreds of kilometres:
    #
    #   gv      the vehicle's attitude with a zero position
    #   ground  a patch of the lunar surface tangent to the sphere straight below the vehicle (it
    #           slides along with the vehicle, turned to the local vertical), relative to the
    #           vehicle
    #   site    the landing-site frame (the world origin) relative to the vehicle: the craters
    #           around the site, and the descent stage left behind by the ascent
    #   plume   the plume's length factor, T / T_ref (for a scale.z binding)
    @inputs begin
        g::Vec{7}, [description = "Vehicle pose (qw, qx, qy, qz, x, y, z)"]
        T::Real, [unit = "N", description = "Thrust"]
    end
    @parameters begin
        R::Real = 1737400.0, [unit = "m", description = "Radius of the Moon"]
        T_ref::Real = 43904.0, [unit = "N", description = "Thrust that draws a plume of nominal length"]
    end
    @variables begin
        rq::Real, [unit = "m"]
        th::Real, [unit = "rad", description = "Angle of the sub-vehicle point from the site, about y"]
    end
    @outputs begin
        gv::Vec{7}
        ground::Vec{7}
        site::Vec{7}
        plume::Real
    end
    @equations begin
        for k in 1:4
            gv[k] ~ g[k]
        end
        gv[5] ~ 0.0
        gv[6] ~ 0.0
        gv[7] ~ 0.0
        rq ~ sqrt(g[5] * g[5] + g[6] * g[6] + (g[7] + R) * (g[7] + R))
        th ~ atan(g[5] / rq, (g[7] + R) / rq)
        ground[1] ~ cos(th / 2)
        ground[2] ~ 0.0
        ground[3] ~ sin(th / 2)
        ground[4] ~ 0.0
        ground[5] ~ R * g[5] / rq - g[5]
        ground[6] ~ R * g[6] / rq - g[6]
        ground[7] ~ (R * (g[7] + R) / rq - R) - g[7]
        site[1] ~ 1.0
        site[2] ~ 0.0
        site[3] ~ 0.0
        site[4] ~ 0.0
        site[5] ~ -g[5]
        site[6] ~ -g[6]
        site[7] ~ -g[7]
        plume ~ T / T_ref
    end
end
