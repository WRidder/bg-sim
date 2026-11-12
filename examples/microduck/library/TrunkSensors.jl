@block TrunkSensors begin
    # What the microduck's IMU and a motion-capture system would read off the free trunk, as
    # scalars a policy host can take one by one: the trunk's angular velocity in the trunk frame
    # (the gyro: the IMU site of the microduck_rl MJCF sits on trunk_base with an identity
    # rotation), its orientation quaternion trunk -> world (w first), its origin in the world,
    # and the projected gravity: the unit vector of gravity in the trunk frame,
    #
    #   g_trunk = R^T (0, 0, -1) = -(R[3,1], R[3,2], R[3,3]),
    #
    # (0, 0, -1) when the trunk is upright, as duck-control/src/obs.rs and mjlab's
    # projected_gravity have it. R is the rotation of the pose quaternion divided by its squared
    # norm, as in the pose blocks, so a drifting norm does not bias it.
    #
    # Inputs: `pose` is the trunk's world pose on the D-MB6 chart (Free3D.pose), `V` the trunk's
    # twist relative to the world in the trunk frame (Free3D.Vrelout with a ground parent).
    @inputs begin
        pose::Vec{7}, [description = "Trunk world pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Trunk twist in the trunk frame (w; v)"]
    end
    @outputs begin
        wx::Real, [unit = "rad/s", description = "Angular velocity about trunk x (forward)"]
        wy::Real, [unit = "rad/s", description = "Angular velocity about trunk y (left)"]
        wz::Real, [unit = "rad/s", description = "Angular velocity about trunk z (up)"]
        qw::Real, [unit = "1", description = "Orientation quaternion, trunk to world, w"]
        qx::Real, [unit = "1", description = "Orientation quaternion x"]
        qy::Real, [unit = "1", description = "Orientation quaternion y"]
        qz::Real, [unit = "1", description = "Orientation quaternion z"]
        x::Real, [unit = "m", description = "Trunk origin, world x"]
        y::Real, [unit = "m", description = "Trunk origin, world y"]
        z::Real, [unit = "m", description = "Trunk origin, world z (the floor is z = 0)"]
        gx::Real, [unit = "1", description = "Projected gravity, trunk x"]
        gy::Real, [unit = "1", description = "Projected gravity, trunk y"]
        gz::Real, [unit = "1", description = "Projected gravity, trunk z (-1 upright)"]
    end
    @variables s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
    @equations begin
        s ~ pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        wx ~ V[1]
        wy ~ V[2]
        wz ~ V[3]
        qw ~ pose[1]
        qx ~ pose[2]
        qy ~ pose[3]
        qz ~ pose[4]
        x ~ pose[5]
        y ~ pose[6]
        z ~ pose[7]
        gx ~ -2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s
        gy ~ -2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s
        gz ~ -(pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s
    end
end
