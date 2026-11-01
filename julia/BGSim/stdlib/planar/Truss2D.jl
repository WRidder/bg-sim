@block Truss2D begin
    # A whole planar pin-jointed truss in one block: `nn` point-mass nodes and `nb` axial bars,
    # given by the node coordinates and the member connectivity as matrices. Each bar is the
    # `AxialBar2D` member (co-rotational axial strain, stiffness-proportional damping, brittle
    # failure by events); each node is the `PointMass2D` inertia with its support.
    #
    # Structure (constants, so they may size arrays and select equations):
    #   conn[k, 1], conn[k, 2]  the end nodes A and B of bar k (1-based node numbers);
    #   fix[i, 1], fix[i, 2]    1 when the x (y) motion of node i is fixed: [1 1] pinned,
    #                           [0 1] roller on a horizontal track, [0 0] free.
    # Geometry and sections (parameters): `xy[i, :]` the reference position of node i,
    # `A[k]`, `I[k]` the area and second moment of bar k (one material E, rho, fy), `mn[i]`
    # extra mass at node i (deck, ballast). Each node carries half the mass rho A L0 of every
    # bar that meets it (lumped masses).
    #
    # Bar k, from node a = conn[k, 1] to b = conn[k, 2]:
    #   L = |r_b - r_a| (exact for any rotation), n = (r_b - r_a)/L, L0 = |xy_b - xy_a|,
    #   N = (1 - broken) E A/L0 (L - L0 + beta n . (v_b - v_a))     tension positive,
    #   force +N n on node a and -N n on node b.
    # Failure (one event pair per bar, a held flag): N > Ft = fy A (tension) or -N > Pcr =
    # pi^2 E I/(K L0)^2 (Euler buckling) and the bar carries no force from then on; the
    # strain energy it held is booked in `Elost`; `nfail` counts the failed bars.
    #
    # Loads: the inputs `Fx`, `Fy` are external forces on the nodes (a `MovingLoad2D`, a
    # `DeckContact2D` vehicle), plus gravity on the node masses (world -y). On a fixed
    # component the node does not move and `Rx`/`Ry` is the support reaction.
    #
    # Energy: `Ebal = Ek + Ee + Eg + Edis + Elost - Wext` is constant (kinetic, strain,
    # gravity (from the reference), dissipated, released by failures, minus the work of the
    # inputs): the block is power-continuous, so this checks the integration.
    @constants begin
        nn::Int = 3, [min = 2, description = "Number of nodes"]
        nb::Int = 3, [min = 1, description = "Number of bars"]
        conn::Mat{nb,2} = [1 2; 2 3; 1 3], [description = "Bar k runs from node conn[k, 1] to node conn[k, 2]"]
        fix::Mat{nn,2} = [1 1; 0 1; 0 0], [description = "fix[i, 1], fix[i, 2]: 1 when the x, y motion of node i is fixed"]
    end
    @inputs begin
        Fx::Vec{nn}, [unit = "N", description = "External force on each node, x"]
        Fy::Vec{nn}, [unit = "N", description = "External force on each node, y"]
    end
    @parameters begin
        xy::Mat{nn,2} = [0.0 0.0; 4.0 0.0; 2.0 2.0], [unit = "m", description = "Reference position of node i: row i = (x, y)"]
        A::Vec{nb} = [0.001, 0.001, 0.001], [unit = "m^2", min = 1.0e-12, description = "Cross-section area of each bar"]
        I::Vec{nb} = [1.0e-6, 1.0e-6, 1.0e-6], [unit = "m^4", min = 0, description = "Second moment of area of each bar (buckling)"]
        mn::Vec{nn} = [0.0, 0.0, 0.0], [unit = "kg", min = 0, description = "Extra mass at each node (deck, ballast)"]
        E::Real = 2.1e11, [unit = "Pa", min = 0, description = "Young's modulus"]
        rho::Real = 7850.0, [unit = "kg/m^3", min = 0, description = "Density of the bars"]
        fy::Real = 3.55e8, [unit = "Pa", min = 0, description = "Tensile strength: a bar fails above Ft = fy A"]
        K::Real = 1.0, [unit = "1", min = 1.0e-6, description = "Effective length factor of the Euler load"]
        beta::Real = 0.0, [unit = "s", min = 0, description = "Stiffness-proportional damping time (axial damping EA beta/L0)"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -y)"]
    end
    @variables begin
        ux::Vec{nn}, [unit = "m", state = :prefer, description = "Node displacement x"]
        uy::Vec{nn}, [unit = "m", state = :prefer, description = "Node displacement y"]
        vx::Vec{nn}, [unit = "m/s", state = :prefer, description = "Node velocity x"]
        vy::Vec{nn}, [unit = "m/s", state = :prefer, description = "Node velocity y"]
        broken::Vec{nb}, [unit = "1", description = "Failure flag of each bar: 0 intact, 1 failed (held)"]
        Elsum::Real = 0.0, [unit = "J", description = "Strain energy released by failed bars"]
        Ed::Real = 0.0, [unit = "J", description = "Energy dissipated by the bar damping"]
        W::Real = 0.0, [unit = "J", description = "Work of the input forces"]
        Ca::Mat{nb,nn}, [unit = "1", description = "Incidence: +1 at the A node of a bar, -1 at its B node"]
        Cm::Mat{nb,nn}, [unit = "1", description = "1 at both end nodes of a bar"]
        mb::Vec{nb}, [unit = "kg", description = "Bar mass rho A L0"]
        mnode::Vec{nn}, [unit = "kg", description = "Node mass"]
        dx::Vec{nb}, [unit = "m", description = "x_b - x_a"]
        dy::Vec{nb}, [unit = "m", description = "y_b - y_a"]
        L0::Vec{nb}, [unit = "m", description = "Rest length"]
        nx::Vec{nb}, [unit = "1", description = "Unit vector a to b, x"]
        ny::Vec{nb}, [unit = "1", description = "Unit vector a to b, y"]
        ext::Vec{nb}, [unit = "m", description = "Elongation L - L0"]
        Ld::Vec{nb}, [unit = "m/s", description = "Elongation rate"]
        Ne::Vec{nb}, [unit = "N", description = "Elastic part of the axial force"]
        Nd::Vec{nb}, [unit = "N", description = "Damping part of the axial force"]
        Nu::Vec{nb}, [unit = "N", description = "Force the bar would carry intact (the sign of util)"]
        fbx::Vec{nb}, [unit = "N", description = "Bar force on its A node, x"]
        fby::Vec{nb}, [unit = "N", description = "Bar force on its A node, y"]
        Fnx::Vec{nn}, [unit = "N", description = "Net force on each node, x"]
        Fny::Vec{nn}, [unit = "N", description = "Net force on each node, y"]
        px::Vec{nn}, [unit = "N*s", description = "Node momentum x"]
        py::Vec{nn}, [unit = "N*s", description = "Node momentum y"]
    end
    @outputs begin
        x::Vec{nn}, [unit = "m"]
        y::Vec{nn}, [unit = "m"]
        xd::Vec{nn}, [unit = "m/s"]
        yd::Vec{nn}, [unit = "m/s"]
        N::Vec{nb}, [unit = "N"]
        util::Vec{nb}, [unit = "1"]
        failed::Vec{nb}, [unit = "1"]
        nfail::Real, [unit = "1", description = "Number of failed bars"]
        L::Vec{nb}, [unit = "m"]
        Ft::Vec{nb}, [unit = "N"]
        Pcr::Vec{nb}, [unit = "N"]
        Rx::Vec{nn}, [unit = "N"]
        Ry::Vec{nn}, [unit = "N"]
        m::Vec{nn}, [unit = "kg"]
        Ek::Real, [unit = "J"]
        Ee::Real, [unit = "J"]
        Eg::Real, [unit = "J"]
        Edis::Real, [unit = "J"]
        Elost::Real, [unit = "J"]
        Wext::Real, [unit = "J"]
        Ebal::Real, [unit = "J"]
    end
    @equations begin
        for k in 1:nb
            for i in 1:nn
                Ca[k, i] ~ ifelse(conn[k, 1] == i, 1.0, ifelse(conn[k, 2] == i, -1.0, 0.0))
                Cm[k, i] ~ ifelse(conn[k, 1] == i, 1.0, ifelse(conn[k, 2] == i, 1.0, 0.0))
            end
            L0[k] ~ sqrt((xy[conn[k, 2], 1] - xy[conn[k, 1], 1]) * (xy[conn[k, 2], 1] - xy[conn[k, 1], 1]) +
                         (xy[conn[k, 2], 2] - xy[conn[k, 1], 2]) * (xy[conn[k, 2], 2] - xy[conn[k, 1], 2]))
            mb[k] ~ rho * A[k] * L0[k]
            dx[k] ~ x[conn[k, 2]] - x[conn[k, 1]]
            dy[k] ~ y[conn[k, 2]] - y[conn[k, 1]]
            L[k] ~ sqrt(dx[k] * dx[k] + dy[k] * dy[k])
            nx[k] ~ dx[k] / L[k]
            ny[k] ~ dy[k] / L[k]
            ext[k] ~ L[k] - L0[k]
            Ld[k] ~ nx[k] * (vx[conn[k, 2]] - vx[conn[k, 1]]) + ny[k] * (vy[conn[k, 2]] - vy[conn[k, 1]])
            Ne[k] ~ (1 - broken[k]) * E * A[k] / L0[k] * ext[k]
            Nd[k] ~ (1 - broken[k]) * E * A[k] / L0[k] * beta * Ld[k]
            N[k] ~ Ne[k] + Nd[k]
            ddt(broken[k]) ~ 0.0
            failed[k] ~ broken[k]
            fbx[k] ~ N[k] * nx[k]
            fby[k] ~ N[k] * ny[k]
            Ft[k] ~ fy * A[k]
            Pcr[k] ~ 9.869604401089358 * E * I[k] / (K * K * L0[k] * L0[k])
            # the switch reads the intact force: N of a failed bar is identically zero, and a
            # switching condition that never leaves zero can trap the event root finder
            Nu[k] ~ E * A[k] / L0[k] * (ext[k] + beta * Ld[k])
            util[k] ~ (1 - broken[k]) * ifelse(Nu[k] > 0, Nu[k] / Ft[k], Nu[k] / Pcr[k])
        end
        mnode ~ mn + 0.5 * transpose(Cm) * mb
        Fnx ~ Fx + transpose(Ca) * fbx
        Fny ~ Fy + transpose(Ca) * fby - g0 * mnode
        for i in 1:nn
            x[i] ~ xy[i, 1] + ux[i]
            y[i] ~ xy[i, 2] + uy[i]
            if fix[i, 1] == 1
                ddt(ux[i]) ~ 0.0
                ddt(vx[i]) ~ 0.0
                Rx[i] ~ -Fnx[i]
            else
                ddt(ux[i]) ~ vx[i]
                ddt(vx[i]) ~ Fnx[i] / mnode[i]
                Rx[i] ~ 0.0
            end
            if fix[i, 2] == 1
                ddt(uy[i]) ~ 0.0
                ddt(vy[i]) ~ 0.0
                Ry[i] ~ -Fny[i]
            else
                ddt(uy[i]) ~ vy[i]
                ddt(vy[i]) ~ Fny[i] / mnode[i]
                Ry[i] ~ 0.0
            end
            xd[i] ~ vx[i]
            yd[i] ~ vy[i]
            px[i] ~ mnode[i] * vx[i]
            py[i] ~ mnode[i] * vy[i]
            m[i] ~ mnode[i]
        end
        ddt(Elsum) ~ 0.0
        ddt(Ed) ~ dot(Nd, Ld)
        ddt(W) ~ dot(Fx, vx) + dot(Fy, vy)
        Ek ~ 0.5 * (dot(px, vx) + dot(py, vy))
        Ee ~ 0.5 * dot(Ne, ext)
        Eg ~ g0 * dot(mnode, uy)
        Edis ~ Ed
        Elost ~ Elsum
        Wext ~ W
        Ebal ~ Ek + Ee + Eg + Ed + Elsum - W
        nfail ~ dot(broken, broken)
    end
    @events begin
        for k in 1:nb
            N[k] > Ft[k] => begin
                reinit(Elsum, Elsum + 0.5 * (1 - broken[k]) * E * A[k] / L0[k] * ext[k] * ext[k])
                reinit(broken[k], 1.0)
            end
            -N[k] > Pcr[k] => begin
                reinit(Elsum, Elsum + 0.5 * (1 - broken[k]) * E * A[k] / L0[k] * ext[k] * ext[k])
                reinit(broken[k], 1.0)
            end
        end
    end
end
