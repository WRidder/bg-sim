@block RocketView begin
    # Poses for the 3D view (a tap: no physics). The view keeps the vehicle at the origin and
    # moves the world: `gv` is the vehicle's attitude with a zero position, `ground` the pose of
    # the launch site relative to the vehicle (the pad falls away below it), and `plume[k]` the
    # length factor of the exhaust plume of stage k (thrust over the stage's reference thrust, and
    # 0 outside the stage's burn window `t_on[k] .. t_off[k]`), for a `scale.z` binding.
    #
    # The launch site turns with the Earth: at the rate `omega` about the world y axis through the
    # Earth's centre (0, 0, -R), the same rate as in `AirData3D`. At omega = 0 it stays put.
    @inputs begin
        g::Vec{7}, [description = "Vehicle pose (qw, qx, qy, qz, x, y, z)"]
        T::Real, [unit = "N", description = "Thrust"]
    end
    @parameters begin
        T_ref::Vec{3} = [1.0e6, 1.0e6, 1.0e6], [unit = "N", description = "Thrust that draws a plume of nominal length, per stage"]
        t_on::Vec{3} = [0.0, 1.0e9, 1.0e9], [unit = "s", description = "Start of the burn window of each stage"]
        t_off::Vec{3} = [1.0e9, 1.0e9, 1.0e9], [unit = "s", description = "End of the burn window of each stage"]
        R::Real = 6378165.0, [unit = "m", description = "Earth radius"]
        omega::Real = 0.0, [unit = "rad/s", description = "Rotation rate of the launch site about the world y axis"]
    end
    @variables begin
        phi::Real, [unit = "rad", description = "Angle the launch site has turned"]
    end
    @outputs begin
        gv::Vec{7}
        ground::Vec{7}
        plume::Vec{3}
    end
    @equations begin
        for k in 1:4
            gv[k] ~ g[k]
        end
        gv[5] ~ 0.0
        gv[6] ~ 0.0
        gv[7] ~ 0.0
        phi ~ omega * t
        ground[1] ~ cos(phi / 2)
        ground[2] ~ 0.0
        ground[3] ~ sin(phi / 2)
        ground[4] ~ 0.0
        ground[5] ~ R * sin(phi) - g[5]
        ground[6] ~ -g[6]
        ground[7] ~ R * (cos(phi) - 1) - g[7]
        for k in 1:3
            plume[k] ~ (ifelse(t >= t_on[k], 1.0, 0.0) - ifelse(t >= t_off[k], 1.0, 0.0)) * T / T_ref[k]
        end
    end
end
