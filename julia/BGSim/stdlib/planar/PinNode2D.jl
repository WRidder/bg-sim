@block PinNode2D begin
    # A truss pin node: a point mass that translates in the plane and passes no moment, with
    # an optional support (pinned or roller). Its single port IS the node's 1-junction, so any
    # number of `Bar2D` ends (and loads) bond to it. The mass is
    # the node's own mass plus its share of the bar masses (half of each bar that meets it).
    #
    #   p (1-junction) ── PointMass2D (I on x, y; zero angular flow; support)
    #
    # `g = (0, x, y)` is the node pose: wire it to the `ga`/`gb` input of every bar at the
    # node. `R` is the support reaction (zero on a free component).
    @constants support::Int = 0, [options = ["free", "pinned", "roller"], description = "Support: 0 free, 1 pinned (x and y fixed), 2 roller (y fixed, x free)"]
    @ports p::Power{Planar}, [frame = "world"]
    @outputs begin
        g::Vec{3}
        v::Vec{2}, [unit = "m/s"]
        R::Vec{2}, [unit = "N"]
        Ek::Real, [unit = "J"]
        Eg::Real, [unit = "J"]
    end
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 1.0e-12, description = "Node mass, including its share of the bar masses"]
        x0::Real = 0.0, [unit = "m", description = "Reference x"]
        y0::Real = 0.0, [unit = "m", description = "Reference y"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -y)"]
    end
    @components begin
        node = Junction(1)
        mass = PointMass2D(support = support, m = m, x0 = x0, y0 = y0, g0 = g0)
    end
    @observables begin
        g = mass.g
        v = mass.v
        R = mass.R
        Ek = mass.Ek
        Eg = mass.Eg
    end
    @connections begin
        connect(p, node)
        connect(node, mass.p)
        connect(mass.g, g)
        connect(mass.v, v)
        connect(mass.R, R)
        connect(mass.Ek, Ek)
        connect(mass.Eg, Eg)
    end
end
