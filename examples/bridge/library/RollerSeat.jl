@block RollerSeat begin
    # A roller bearing on a seat of finite length, for a `Truss2D` node that is free in the
    # truss (fix [0 0]): the seat carries the node vertically while it stays on the seat, and
    # lets it fall once it has rolled off.
    #
    #   travel = x[node] - x0                  the roll along the seat (x0: the seat centre)
    #   pen    = y0 - y[node]                  how far the node presses into the seat
    #   R      = (1 - unseated) k max(pen, 0)  the seat reaction (up): unilateral, it pushes
    #                                          but never pulls, so the end can lift off
    #   unseated: a held flag set by an event when |travel| > seat (the node rolls off an edge)
    #
    # The block sits in the force path from the loads to the truss: it passes Fxin, Fyin on
    # and adds R to the node's y force. The seat is a stiff spring (k, no damping), so it books
    # its own energy: Es = k max(pen, 0)^2 / 2 is stored in it, the work it does on the truss is
    # W = integral R yd[node] dt (the truss counts it in its Wext), and the spring energy it holds
    # when the node rolls off goes to Elost. Ebal = Es + Elost + W is constant (and the truss's
    # own Ebal stays constant through the unseating, as for any input force).
    #
    # Start the node at its seated equilibrium, uy = -R / k, so the run starts at rest.
    @constants begin
        nn::Int = 2, [min = 1, description = "Number of truss nodes"]
        node::Int = 1, [min = 1, description = "The node on the seat"]
    end
    @inputs begin
        Fxin::Vec{nn}, [unit = "N", description = "Node forces x from the loads"]
        Fyin::Vec{nn}, [unit = "N", description = "Node forces y from the loads"]
        x::Vec{nn}, [unit = "m", description = "Node x positions (truss output x)"]
        y::Vec{nn}, [unit = "m", description = "Node y positions (truss output y)"]
        yd::Vec{nn}, [unit = "m/s", description = "Node y velocities (truss output yd)"]
    end
    @outputs begin
        Fx::Vec{nn}, [unit = "N"]
        Fy::Vec{nn}, [unit = "N"]
        R::Real, [unit = "N", description = "Seat reaction on the node (up)"]
        travel::Real, [unit = "m", description = "Roll of the node along the seat"]
        unseated::Real, [unit = "1", description = "1 once the node has rolled off the seat"]
        Es::Real, [unit = "J", description = "Energy stored in the seat spring"]
        W::Real, [unit = "J", description = "Work of the seat on the truss"]
        Elost::Real, [unit = "J", description = "Spring energy released when the node rolled off"]
        Ebal::Real, [unit = "J", description = "Es + Elost + W: constant"]
    end
    @parameters begin
        x0::Real = 0.0, [unit = "m", description = "Seat centre: the node's rest x"]
        y0::Real = 0.0, [unit = "m", description = "Seat height: the node's rest y"]
        seat::Real = 0.3, [unit = "m", min = 0, description = "Travel to either seat edge"]
        k::Real = 2.0e9, [unit = "N/m", min = 0, description = "Seat stiffness"]
    end
    @variables begin
        off::Real = 0.0, [unit = "1", description = "Unseated flag (held)"]
        Wi::Real = 0.0, [unit = "J", description = "Work of the seat on the truss"]
        El::Real = 0.0, [unit = "J", description = "Released spring energy"]
        pen::Real, [unit = "m", description = "Seat penetration"]
        pp::Real, [unit = "m", description = "max(pen, 0)"]
    end
    @equations begin
        travel ~ x[node] - x0
        pen ~ y0 - y[node]
        pp ~ max(pen, 0.0)
        R ~ (1 - off) * k * pp
        for i in 1:nn
            Fx[i] ~ Fxin[i]
            if i == node
                Fy[i] ~ Fyin[i] + R
            else
                Fy[i] ~ Fyin[i]
            end
        end
        ddt(off) ~ 0.0
        unseated ~ off
        ddt(Wi) ~ R * yd[node]
        ddt(El) ~ 0.0
        Es ~ (1 - off) * 0.5 * k * pp * pp
        W ~ Wi
        Elost ~ El
        Ebal ~ Es + El + Wi
    end
    @events begin
        travel > seat => begin
            reinit(El, El + (1 - off) * 0.5 * k * max(pen, 0.0) * max(pen, 0.0))
            reinit(off, 1.0)
        end
        -travel > seat => begin
            reinit(El, El + (1 - off) * 0.5 * k * max(pen, 0.0) * max(pen, 0.0))
            reinit(off, 1.0)
        end
    end
end
