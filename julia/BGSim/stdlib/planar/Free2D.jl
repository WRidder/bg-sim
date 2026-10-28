@block Free2D begin
    # A free (floating-base) planar body: `RigidBody2D` plus the pose integrator, driven by
    # the body's own twist. One power port (apply a wrench with `ExternalWrenchPlanar` or bond
    # it to another body), and an algebraic pose output for the controller and the viewer.
    #
    # Only floating bases integrate a pose (D-MB6). The signal path `V -> PoseIntegrator2D ->
    # g -> body.g` is differential, not algebraic: the pose components are states, so gravity
    # reads the integrated pose without an algebraic loop.
    @ports p::Power{Planar}
    @outputs g::Vec{3}
    @outputs P::Vec{3}
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        J::Real = 0.01, [unit = "kg*m^2", min = 0, description = "Yaw inertia about the centre of mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        theta0::Real = 0.0, [unit = "rad", description = "Initial angle"]
        x0::Real = 0.0, [unit = "m", description = "Initial x"]
        y0::Real = 0.0, [unit = "m", description = "Initial y"]
    end
    @components begin
        body = RigidBody2D(m = m, J = J, g0 = g0)
        pose = PoseIntegrator2D(theta0 = theta0, x0 = x0, y0 = y0)
    end
    @connections begin
        connect(p, body.p)
        connect(body.V, pose.tw)
        connect(pose.g, body.g)
        connect(pose.g, g)
        connect(body.P, P)
    end
end
