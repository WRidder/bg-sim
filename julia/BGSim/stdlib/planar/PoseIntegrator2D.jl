@block PoseIntegrator2D begin
    # Floating-base pose integrator (D-MB6): the SE(2) chart g = (theta, x, y) integrated from
    # the body-frame twist tw = [omega; vx; vy]:
    #
    #     ddt(theta) = omega
    #     ddt(p)     = R(theta) [vx, vy]
    #
    # There is no `exp` integrator and no quaternion: the planar pose is two coordinates plus
    # an angle, all vector-space states. Fixed-base links never use this block; their pose is
    # composed algebraically (`ComposePose2D`, `JointPose2D`).
    #
    # The states are the *increments* of the pose (`theta0 + th`, `x0 + xi`, `y0 + yi`), so the
    # initial pose is a parameter rather than a start value (D4: parameter-only reruns stay
    # live in the compile cache).
    @inputs tw::Vec{3}
    @parameters begin
        theta0::Real = 0.0, [unit = "rad", description = "Initial angle"]
        x0::Real = 0.0, [unit = "m", description = "Initial x"]
        y0::Real = 0.0, [unit = "m", description = "Initial y"]
    end
    @variables begin
        th::Real = 0.0, [unit = "rad", state = :prefer, description = "Angle increment"]
        xi::Real = 0.0, [unit = "m", state = :prefer, description = "x increment"]
        yi::Real = 0.0, [unit = "m", state = :prefer, description = "y increment"]
    end
    @outputs g::Vec{3}
    @equations begin
        ddt(th) ~ tw[1]
        ddt(xi) ~ cos(theta0 + th) * tw[2] - sin(theta0 + th) * tw[3]
        ddt(yi) ~ sin(theta0 + th) * tw[2] + cos(theta0 + th) * tw[3]
        g[1] ~ theta0 + th
        g[2] ~ x0 + xi
        g[3] ~ y0 + yi
    end
end
