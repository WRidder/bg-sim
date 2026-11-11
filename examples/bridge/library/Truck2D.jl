@block Truck2D begin
    # A two-axle lorry crossing the deck of a `Truss2D`, as one planar rigid body (the half of
    # the lorry carried by this truss): a `RigidBody2D` on a `PoseIntegrator2D` (a floating
    # base), the tyres on the deck through `DeckContact2D` (one wheel per axle at (rx, ry) in the
    # body frame, bonded to the body through the 1-junction `hub`), and `Cruise` driving it at the set
    # speed through the tyre traction.
    #
    #   deck nodes (x, y, xd, yd) --> contact --> node forces (Fx, Fy) --> truss
    #                                    |  bond
    #   cruise (F) -------------------> body <-- pose (g) --> view (3D pose, wheel angle)
    #
    # Start the body in the pose (0, x0, y0) with its momentum m (0, v, 0) (a start of
    # `body/inertia/P`), so it rolls in at the set speed on its statically deflected tyres.
    @constants begin
        nn::Int = 3, [min = 2, description = "Number of truss nodes"]
        nd::Int = 2, [min = 2, description = "Deck nodes: nodes 1..nd of the truss, left to right"]
    end
    @inputs begin
        x::Vec{nn}, [unit = "m", description = "Node x positions (truss output x)"]
        y::Vec{nn}, [unit = "m", description = "Node y positions (truss output y)"]
        xd::Vec{nn}, [unit = "m/s", description = "Node x velocities (truss output xd)"]
        yd::Vec{nn}, [unit = "m/s", description = "Node y velocities (truss output yd)"]
    end
    @outputs begin
        Fx::Vec{nn}, [unit = "N"]
        Fy::Vec{nn}, [unit = "N"]
    end
    @parameters begin
        m::Real = 10000.0, [unit = "kg", min = 1.0e-6, description = "Mass carried by this truss (half the lorry)"]
        J::Real = 6.0e4, [unit = "kg*m^2", min = 1.0e-6, description = "Pitch inertia (half the lorry)"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        x0::Real = -25.0, [unit = "m", description = "Start x of the centre of mass"]
        y0::Real = 1.5, [unit = "m", description = "Start y of the centre of mass"]
        rx::Vec{2} = [2.0, -2.0], [unit = "m", description = "Axle x in the body frame (front, rear)"]
        ry::Vec{2} = [-1.0, -1.0], [unit = "m", description = "Axle y in the body frame"]
        r::Real = 0.5, [unit = "m", min = 1.0e-6, description = "Wheel radius"]
        k::Real = 1.5e6, [unit = "N/m", min = 0, description = "Tyre stiffness per axle"]
        c::Real = 2.0e4, [unit = "N*s/m", min = 0, description = "Tyre damping per axle"]
        v_set::Real = 10.0, [unit = "m/s", description = "Set speed"]
        tau::Real = 0.5, [unit = "s", min = 1.0e-3, description = "Speed-control time constant"]
        depth::Real = 0.0, [unit = "m", description = "World y of the lorry in the 3D view"]
    end
    @components begin
        hub = Junction(1)
        body = RigidBody2D(m = m, J = J, g0 = g0)
        pose = PoseIntegrator2D(theta0 = 0.0, x0 = x0, y0 = y0)
        contact = DeckContact2D(nn = nn, nd = nd, nw = 2, rx = rx, ry = ry, r = r, k = k, c = c)
        cruise = Cruise(m = m, tau = tau, v_set = v_set)
        view = PlanarPose3D(depth = depth, r = r)
    end
    @observables begin
        g = pose.g
        v = cruise.v
        fn = contact.fn
        delta = contact.delta
        F = cruise.F
        q = view.q
        wheel = view.wheel
    end
    @connections begin
        connect(hub, contact.p)
        connect(hub, body.p)
        connect(body.V, pose.tw)
        connect(pose.g, body.g)
        connect(pose.g, contact.g)
        connect(x, contact.x)
        connect(y, contact.y)
        connect(xd, contact.xd)
        connect(yd, contact.yd)
        connect(body.V, cruise.V)
        connect(cruise.F, contact.Fd)
        connect(pose.g, view.g)
        connect(contact.Fx, Fx)
        connect(contact.Fy, Fy)
    end
end
