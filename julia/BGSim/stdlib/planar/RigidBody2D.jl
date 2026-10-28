@block RigidBody2D begin
    # A planar rigid body as a *composite* (plan 5.2): the single power port IS the body's
    # 1-junction, and the flat graph contains only documented primitives:
    #
    #            attachment transform (outside)
    #                     |
    #   p (1-junction) ── IPlanar ── Pm ──► CoriolisPlanar
    #                     |
    #                  GravityPlanar ◄── g (world pose from ComposePose2D)
    #
    # One port only (D-MB4): attachments are external transforms, and a multi-port body is
    # built from copies of this block plus `FixedJoint2D`/`Revolute2D`. The inertia `J`/`m`
    # and the matrix live only in `IPlanar`; `CoriolisPlanar` sees only the momentum `Pm`
    # (D-MB3), so no inertia is duplicated.
    #
    # Signals: `V` is the body twist (component-wise, in the body frame), `P` the momentum
    # `I.P`, `g` the pose input (readable at the composite path), `p.e[k]`/`p.f[k]`/`p.P` the
    # port effort/flow/power. The twist comes from a zero-power `DfPlanar` on the 1-junction
    # (`V[k] = p.f[k]`, checked by the element tests), so a floating base can integrate its
    # pose from it (D-MB6).
    @ports p::Power{Planar}, [frame = "body"]
    @inputs g::Vec{3}
    @outputs V::Vec{3}
    @outputs P::Vec{3}
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        J::Real = 0.01, [unit = "kg*m^2", min = 0, description = "Yaw inertia about the centre of mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @components begin
        node = Junction(1)
        inertia = IPlanar(J = J, m = m)
        coriolis = CoriolisPlanar()
        gravity = GravityPlanar(m = m, g0 = g0)
        flow = DfPlanar()
    end
    @connections begin
        connect(p, node)
        connect(inertia.p, node)
        connect(coriolis.p, node)
        connect(gravity.p, node)
        connect(flow.p, node)
        connect(g, gravity.g)
        connect(inertia.Pm, coriolis.P)
        connect(inertia.Pm, P)
        connect(flow.y, V)
    end
end
