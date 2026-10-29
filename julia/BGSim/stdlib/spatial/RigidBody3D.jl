@block RigidBody3D begin
    # A spatial rigid body as a *composite* (plan 5.2), the spatial twin of `RigidBody2D`:
    # the single power port IS the body's 1-junction, and the flat graph contains only
    # documented primitives:
    #
    #            attachment transform (outside)
    #                     |
    #   p (1-junction) ── ISpatial ── Pm ──► CoriolisSpatial
    #                     |
    #                GravitySpatial ◄── g (world pose from ComposePose3D)
    #
    # One port only (D-MB4): attachments are external transforms. The diagonal principal
    # inertia `J`/`m` and the matrix live only in `ISpatial`; `CoriolisSpatial` sees only the
    # momentum `Pm` (D-MB3), so no inertia is duplicated.
    #
    # Signals: `V` is the body twist `[w; v]` (component-wise, in the body frame), `P` the
    # momentum `ISpatial.P`, `g` the pose input (the D-MB6 chart `(q_w, q_x, q_y, q_z, p)`,
    # readable at the composite path), and `p.e[k]`/`p.f[k]`/`p.P` the port effort/flow/power.
    # The twist comes from a zero-power `DfSpatial` on the 1-junction (`V[k] = p.f[k]`), so a
    # floating base can integrate its pose from it (D-MB6). Fixed-base links compose their
    # pose from the joint coordinate (`ComposePose3D`) and never integrate one.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs g::Vec{7}
    @outputs V::Vec{6}
    @outputs P::Vec{6}
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        J::Vec{3} = [0.1, 0.1, 0.1], [unit = "kg*m^2", description = "Principal moments of inertia about the centre of mass (J[k] > 0)"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @components begin
        node = Junction(1)
        inertia = ISpatial(J = J, m = m)
        coriolis = CoriolisSpatial()
        gravity = GravitySpatial(m = m, g0 = g0)
        flow = DfSpatial()
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
