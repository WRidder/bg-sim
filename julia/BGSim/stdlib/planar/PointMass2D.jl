@block PointMass2D begin
    # A point mass in the plane that translates but never turns: the inertia of a truss pin
    # node (the atomic core of `PinNode2D`). The port is a planar multibond whose twist is
    # (omega, vx, vy) in the world frame; the node has no rotational inertia, so its angular
    # flow is held at zero (a pin passes no moment, so no torque ever reaches it) and the
    # translation is an `I` element in integral causality:
    #
    #     ddt(P) = (p.e[2], p.e[3] - m g0),   (p.f[2], p.f[3]) = P / m,   p.f[1] = 0
    #
    # `support` (structural) fixes degrees of freedom: 1 pinned (x and y fixed), 2 roller
    # (y fixed, x free). A fixed component is a flow source of zero, and `R` reports the
    # support reaction on the node (the force the support has to deliver). The pose output
    # `g = (0, x, y)` is the planar D-MB6 chart, so a bar reads the node position from it.
    # The displacement `u` from the reference position (x0, y0) is the state, so the
    # reference geometry is a parameter (parameter-only reruns stay in the compile cache).
    @constants support::Int = 0, [options = ["free", "pinned", "roller"], description = "Support: 0 free, 1 pinned (x and y fixed), 2 roller (y fixed, x free)"]
    @ports p::Power{Planar}, [frame = "world"]
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 1.0e-12, description = "Node mass, including its share of the bar masses"]
        x0::Real = 0.0, [unit = "m", description = "Reference x"]
        y0::Real = 0.0, [unit = "m", description = "Reference y"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -y)"]
    end
    @variables begin
        P::Vec{2} = [0.0, 0.0], [unit = "N*s", state = :prefer, description = "Linear momentum"]
        u::Vec{2} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Displacement from (x0, y0)"]
    end
    @outputs begin
        g::Vec{3}
        v::Vec{2}, [unit = "m/s"]
        R::Vec{2}, [unit = "N"]
        Ek::Real, [unit = "J"]
        Eg::Real, [unit = "J"]
    end
    @equations begin
        p.f[1] ~ 0.0
        if support == 1
            ddt(P[1]) ~ 0.0
        else
            ddt(P[1]) ~ p.e[2]
        end
        if support == 0
            ddt(P[2]) ~ p.e[3] - m * g0
        else
            ddt(P[2]) ~ 0.0
        end
        if support == 1
            p.f[2] ~ 0.0
        else
            p.f[2] ~ P[1] / m
        end
        if support == 0
            p.f[3] ~ P[2] / m
        else
            p.f[3] ~ 0.0
        end
        ddt(u[1]) ~ p.f[2]
        ddt(u[2]) ~ p.f[3]
        if support == 1
            R[1] ~ -p.e[2]
        else
            R[1] ~ 0.0
        end
        if support == 0
            R[2] ~ 0.0
        else
            R[2] ~ m * g0 - p.e[3]
        end
        g[1] ~ 0.0
        g[2] ~ x0 + u[1]
        g[3] ~ y0 + u[2]
        v[1] ~ p.f[2]
        v[2] ~ p.f[3]
        Ek ~ 0.5 * (P[1] * p.f[2] + P[2] * p.f[3])
        Eg ~ m * g0 * u[2]
    end
    @causality p => :flow_out
    @orientation p => :in
end
