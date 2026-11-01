@block PlanarPose3D begin
    # The 3D viewer pose of a planar body: the plane (x, y) of the model is the world x-z plane
    # of the scene (z up), at the world y = `depth`. A planar angle theta (counter-clockwise in
    # x-y) is a turn about the world -y axis, so the pose (qw, qx, qy, qz, x, y, z) is
    #
    #     (cos(theta/2), 0, -sin(theta/2), 0, x, depth, y)
    #
    # `wheel` is the rolling angle -x/r of a wheel of radius r (for a joint position binding;
    # turning about the world +y axis, so a wheel rolling to +x turns by -x/r).
    @inputs g::Vec{3}
    @outputs begin
        q::Vec{7}
        wheel::Real, [unit = "rad"]
    end
    @parameters begin
        depth::Real = 0.0, [unit = "m", description = "World y of the model plane"]
        r::Real = 0.5, [unit = "m", min = 1.0e-6, description = "Wheel radius"]
    end
    @equations begin
        q[1] ~ cos(g[1] / 2)
        q[2] ~ 0.0
        q[3] ~ -sin(g[1] / 2)
        q[4] ~ 0.0
        q[5] ~ g[2]
        q[6] ~ depth
        q[7] ~ g[3]
        wheel ~ -g[2] / r
    end
end
