@block JointPose2D begin
    # The joint-pose chart of a joint coordinate: g(q) = (q + theta0, rx, ry) on the SE(2)
    # chart. It is the fixed part of a joint's kinematics that has to stay outside the native
    # joint block once the joint is a bond-graph composite (`Revolute2DRigid`), and the pose
    # a `GravityPlanar`/`ComposePose2D` chain consumes.
    #
    # `theta0` is the initial angle of the joint coordinate (the integrator's start is zero,
    # so the physical angle is the integrated rate plus `theta0`); `rx`/`ry` are the child
    # origin in the parent frame (the pivot position).
    @inputs q::Real, [unit = "rad"]
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Child origin x in the parent frame"]
        ry::Real = 0.0, [unit = "m", description = "Child origin y in the parent frame"]
        theta0::Real = 0.0, [unit = "rad", description = "Initial joint angle"]
    end
    @outputs g::Vec{3}
    @equations begin
        g[1] ~ q + theta0
        g[2] ~ rx
        g[3] ~ ry
    end
end
