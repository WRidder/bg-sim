@block ImpactBody3D begin
    # A spatial rigid body (the composite of `RigidBody3D`) whose single port `p` is the
    # **pivot frame** of a `SwitchedPivot3D`, with the impact map of J-MB14 built in. The
    # pivot frame is the body-centre-of-mass frame translated so that the CoM sits at `c = (cx, cy, cz)` in it (axes
    # parallel to the principal axes; v1 limit):
    #
    #   p (pivot frame) -- mount(c) -- 1-junction (CoM) -- ImpactInertia3D (J, m, c, P)
    #                                        |-- CoriolisSpatial (fed by ImpactInertia3D/Pm)
    #                                        |-- GravitySpatial (fed by the CoM world pose g)
    #
    # `c` is a single parameter set: it feeds the mount **and** the inertia block, so the
    # effective pivot inertia the impact map uses is assembled from `J`, `m` and the very
    # offset the mount applies (never a copy). The impact is applied when the guard `sw`
    # crosses 0.5 upward (the same signal as `SwitchedPivot3D.sw`) with `mode_new`.
    #
    # Scope (v1): the impacted subtree is this one rigid body. A body that is bonded to
    # further bodies behind its pivot is not supported (the momentum projection only sees this
    # body's `P`); model such a mechanism with compliant joints instead.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs begin
        g::Vec{7}
        sw::Real
        mode_new::Real
    end
    @outputs V::Vec{6}
    @outputs P::Vec{6}
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        J::Vec{3} = [0.1, 0.1, 0.1], [unit = "kg*m^2", description = "Principal moments of inertia about the centre of mass (J[k] > 0)"]
        cx::Real = 0.0, [unit = "m", description = "Body centre of mass x in the pivot frame"]
        cy::Real = 0.0, [unit = "m", description = "Body centre of mass y in the pivot frame"]
        cz::Real = 0.0, [unit = "m", description = "Body centre of mass z in the pivot frame"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @components begin
        node = Junction(1)
        mount = FixedTransform3DNeutral(x = cx, y = cy, z = cz)
        inertia = ImpactInertia3D(J = J, m = m, cx = cx, cy = cy, cz = cz)
        coriolis = CoriolisSpatial()
        gravity = GravitySpatial(m = m, g0 = g0)
        flow = DfSpatial()
    end
    @connections begin
        connect(p, mount.a)
        connect(mount.b, node)
        connect(inertia.p, node)
        connect(coriolis.p, node)
        connect(gravity.p, node)
        connect(flow.p, node)
        connect(g, gravity.g)
        connect(sw, inertia.sw)
        connect(mode_new, inertia.mode_new)
        connect(inertia.Pm, coriolis.P)
        connect(inertia.Pm, P)
        connect(flow.y, V)
    end
end
