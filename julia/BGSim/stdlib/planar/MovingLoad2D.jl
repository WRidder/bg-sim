@block MovingLoad2D begin
    # A vertical point load that travels along the deck of a `Truss2D` at a constant speed,
    # shared between the deck nodes by linear (hat) shape functions: between deck nodes j and
    # j + 1 at the fraction xi of the panel, node j carries (1 - xi) P and node j + 1 xi P,
    # which is the consistent nodal load of a point load on a simply supported deck panel.
    #
    # The deck is the polyline of nodes 1..nd of the truss, numbered left to right (put the
    # deck nodes first). The input `x` is the truss output `x` (current node positions), so
    # the load follows the deformed deck. Off the deck (s < x[1] or s > x[nd]) the load is
    # zero. The outputs feed the truss inputs `Fx`, `Fy`.
    #
    #   s(t) = s0 + v t,   Fy[j] = -P w_j(s),   w_j = hat function of deck node j.
    @constants begin
        nn::Int = 3, [min = 2, description = "Number of truss nodes"]
        nd::Int = 2, [min = 2, description = "Deck nodes: nodes 1..nd of the truss, left to right"]
    end
    @inputs x::Vec{nn}, [unit = "m", description = "Node x positions (the truss output x)"]
    @parameters begin
        P::Real = 1.0e4, [unit = "N", description = "Load, acting downward (world -y)"]
        s0::Real = 0.0, [unit = "m", description = "Load position at t = 0"]
        v::Real = 0.0, [unit = "m/s", description = "Travel speed (0: a static load at s0)"]
    end
    @variables w::Vec{nd}, [unit = "1", description = "Shape function of each deck node at the load"]
    @outputs begin
        Fx::Vec{nn}, [unit = "N"]
        Fy::Vec{nn}, [unit = "N"]
        s::Real, [unit = "m"]
    end
    @equations begin
        s ~ s0 + v * t
        w[1] ~ ifelse(s >= x[1], max(0.0, (x[2] - s) / (x[2] - x[1])), 0.0)
        for j in 2:(nd - 1)
            w[j] ~ max(0.0, min((s - x[j - 1]) / (x[j] - x[j - 1]), (x[j + 1] - s) / (x[j + 1] - x[j])))
        end
        w[nd] ~ ifelse(s <= x[nd], max(0.0, (s - x[nd - 1]) / (x[nd] - x[nd - 1])), 0.0)
        for i in 1:nn
            Fx[i] ~ 0.0
        end
        for j in 1:nd
            Fy[j] ~ -P * w[j]
        end
        for i in (nd + 1):nn
            Fy[i] ~ 0.0
        end
    end
end
