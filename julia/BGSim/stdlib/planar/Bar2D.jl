@block Bar2D begin
    # A truss bar: an axial two-force member between two pin nodes (`PinNode2D`), with
    # co-rotational axial strain (exact for any rotation), stiffness-proportional damping and
    # brittle failure by events (tension above Ft = fy A, compression above the Euler load
    # pi^2 E I / (K L0)^2). A failed bar carries no force from then on. The physics is in
    # `AxialBar2D`; this composite gives each end its own 1-junction, so the ends bond to a
    # node like a body port.
    #
    #   a (1-junction) ── AxialBar2D.pa      AxialBar2D.pb ── b (1-junction)
    #             ga, gb (node poses) ──► length, direction
    #
    # The bar is unstressed at the node positions of t = 0. Its mass rho A L0 (output `m`)
    # belongs to the nodes: add half of it to each end node's `m`.
    @ports begin
        a::Power{Planar}, [frame = "world"]
        b::Power{Planar}, [frame = "world"]
    end
    @inputs begin
        ga::Vec{3}, [description = "Pose (theta, x, y) of node A"]
        gb::Vec{3}, [description = "Pose (theta, x, y) of node B"]
    end
    @outputs begin
        N::Real, [unit = "N"]
        util::Real, [unit = "1"]
        broken::Real, [unit = "1"]
        L::Real, [unit = "m"]
        Ft::Real, [unit = "N"]
        Pcr::Real, [unit = "N"]
        m::Real, [unit = "kg"]
        Ee::Real, [unit = "J"]
        Edis::Real, [unit = "J"]
        Elost::Real, [unit = "J"]
    end
    @parameters begin
        E::Real = 2.1e11, [unit = "Pa", min = 0, description = "Young's modulus"]
        A::Real = 1.0e-3, [unit = "m^2", min = 1.0e-12, description = "Cross-section area"]
        I::Real = 1.0e-6, [unit = "m^4", min = 0, description = "Second moment of area (buckling)"]
        rho::Real = 7850.0, [unit = "kg/m^3", min = 0, description = "Density (bar mass rho A L0, carried by the end nodes)"]
        fy::Real = 3.55e8, [unit = "Pa", min = 0, description = "Tensile strength: the bar fails above Ft = fy A"]
        K::Real = 1.0, [unit = "1", min = 1.0e-6, description = "Effective length factor of the Euler load"]
        beta::Real = 0.0, [unit = "s", min = 0, description = "Stiffness-proportional damping time (axial damping EA beta/L0)"]
    end
    @components begin
        nodeA = Junction(1)
        nodeB = Junction(1)
        bar = AxialBar2D(E = E, A = A, I = I, rho = rho, fy = fy, K = K, beta = beta)
    end
    @observables begin
        N = bar.N
        util = bar.util
        broken = bar.brokenout
        L = bar.L
        Ft = bar.Ft
        Pcr = bar.Pcr
        m = bar.m
        Ee = bar.Ee
        Edis = bar.Edis
        Elost = bar.Elostout
    end
    @connections begin
        connect(a, nodeA)
        connect(nodeA, bar.pa)
        connect(b, nodeB)
        connect(nodeB, bar.pb)
        connect(ga, bar.ga)
        connect(gb, bar.gb)
        connect(bar.N, N)
        connect(bar.util, util)
        connect(bar.brokenout, broken)
        connect(bar.L, L)
        connect(bar.Ft, Ft)
        connect(bar.Pcr, Pcr)
        connect(bar.m, m)
        connect(bar.Ee, Ee)
        connect(bar.Edis, Edis)
        connect(bar.Elostout, Elost)
    end
end
