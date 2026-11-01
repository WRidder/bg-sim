@block DeckContact2D begin
    # Compliant wheel-on-deck contact between a planar body (a vehicle) and the deck of a
    # `Truss2D`: `nw` wheels, rigidly mounted on the body at (rx[w], ry[w]) in the body frame,
    # roll on the deck polyline of truss nodes 1..nd (left to right; put the deck nodes first).
    #
    # Per wheel w and deck panel j (nodes a = j, b = j + 1, unit tangent t), with the wheel
    # centre c and the closest point q of the panel *segment* to it:
    #   xi    = (c - r_a) . t / |r_b - r_a|         where c projects on the panel line
    #   xc    = clamp(xi, 0, 1)                     q = (1 - xc) r_a + xc r_b
    #   n     = (c - q) / |c - q|                   contact normal (the panel normal, or the
    #                                               direction from a deck node over a crest)
    #   delta = r - |c - q|                         tyre deflection (positive in contact)
    #   delta' = -n . (v_c - (1 - xc) v_a - xc v_b) its exact rate (the panel turns as well)
    #   f     = delta (k + c delta'/dref)            tyre spring and Hunt-Crossley damper
    # The damping grows with the deflection (it is c at delta = dref), so the force is continuous
    # when a wheel lands or lifts off and needs no clamp at zero (a clamp would make the
    # integrator chatter on f = 0 while a tyre extends); it pulls only for delta' < -k dref/c.
    # One panel carries a wheel: panel j while the wheel centre is between the bisectors of the
    # deck angles at nodes j and j + 1,
    #   b_j = (c - r_j) . (t_(j-1) + t_j) >= 0   and   b_(j+1) < 0,
    # and its deflection is positive. On a bisector both panels give the same deflection (over
    # a sag the two panel lines are equally far; over a crest both segments end on the node),
    # so the wheel rolls over a sag on the deeper panel and over a crest on the node itself, and
    # the force is continuous at every deck node. The switches are clean zero crossings of b_j.
    # The wheel gets f n plus the traction tau t (each wheel on the deck drives Fd / nw); the deck
    # gets the opposite, distributed to its two nodes by the shape functions (1 - xc, xc). The
    # normal force is the gradient of the tyre energy with respect to the wheel and both
    # nodes, so the contact is energy-consistent; the traction does the drive's work.
    #
    # Port and sign: bond FROM this port TO the body's port, as for `ExternalWrenchPlanar`
    # (the opposite bond direction reverses the wheel forces). The port flow is the body twist
    # (omega, vx, vy) in the body frame, `g` the body pose (theta, x, y), and the port effort
    # is minus the wheel wrench on the body. The outputs `Fx`, `Fy` are the forces on the
    # truss nodes: wire them to the truss inputs.
    @constants begin
        nn::Int = 3, [min = 2, description = "Number of truss nodes"]
        nd::Int = 2, [min = 2, description = "Deck nodes: nodes 1..nd of the truss, left to right"]
        nw::Int = 2, [min = 1, description = "Number of wheels"]
    end
    @ports p::Power{Planar}, [frame = "body"]
    @inputs begin
        g::Vec{3}, [description = "Body pose (theta, x, y)"]
        x::Vec{nn}, [unit = "m", description = "Node x positions (truss output x)"]
        y::Vec{nn}, [unit = "m", description = "Node y positions (truss output y)"]
        xd::Vec{nn}, [unit = "m/s", description = "Node x velocities (truss output xd)"]
        yd::Vec{nn}, [unit = "m/s", description = "Node y velocities (truss output yd)"]
        Fd::Real, [unit = "N", description = "Drive force along the deck, Fd / nw per wheel on the deck"]
    end
    @parameters begin
        rx::Vec{nw} = [1.5, -1.5], [unit = "m", description = "Wheel centre x in the body frame"]
        ry::Vec{nw} = [-0.5, -0.5], [unit = "m", description = "Wheel centre y in the body frame"]
        r::Real = 0.5, [unit = "m", min = 1.0e-6, description = "Wheel radius"]
        k::Real = 1.0e6, [unit = "N/m", min = 0, description = "Tyre stiffness per wheel"]
        c::Real = 1.0e4, [unit = "N*s/m", min = 0, description = "Tyre damping per wheel at the deflection dref"]
        dref::Real = 0.03, [unit = "m", min = 1.0e-9, description = "Reference deflection of the damping"]
    end
    @variables begin
        ct::Real = 1.0, [unit = "1", description = "cos(theta)"]
        st::Real = 0.0, [unit = "1", description = "sin(theta)"]
        Ls::Vec{nd - 1}, [unit = "m", description = "Panel length"]
        tx::Vec{nd - 1}, [unit = "1", description = "Panel tangent x"]
        ty::Vec{nd - 1}, [unit = "1", description = "Panel tangent y"]
        cx::Vec{nw}, [unit = "m", description = "Wheel centre x"]
        cy::Vec{nw}, [unit = "m", description = "Wheel centre y"]
        vcx::Vec{nw}, [unit = "m/s", description = "Wheel centre velocity x"]
        vcy::Vec{nw}, [unit = "m/s", description = "Wheel centre velocity y"]
        xi::Mat{nw,nd - 1}, [unit = "1", description = "Projection of wheel w on the line of panel j"]
        xc::Mat{nw,nd - 1}, [unit = "1", description = "Projection clamped to the panel, 0..1"]
        dx::Mat{nw,nd - 1}, [unit = "m", description = "Wheel centre minus closest panel point, x"]
        dy::Mat{nw,nd - 1}, [unit = "m", description = "Wheel centre minus closest panel point, y"]
        dist::Mat{nw,nd - 1}, [unit = "m", description = "Distance of the wheel centre to panel j"]
        nx::Mat{nw,nd - 1}, [unit = "1", description = "Contact normal x"]
        ny::Mat{nw,nd - 1}, [unit = "1", description = "Contact normal y"]
        del::Mat{nw,nd - 1}, [unit = "m", description = "Tyre deflection of wheel w on panel j"]
        deld::Mat{nw,nd - 1}, [unit = "m/s", description = "Rate of del"]
        bs::Mat{nw,nd}, [unit = "m", description = "Side of wheel w of the deck-angle bisector at node i (r and -r at the ends)"]
        on::Mat{nw,nd - 1}, [unit = "1", description = "1 while panel j carries wheel w"]
        fc::Mat{nw,nd - 1}, [unit = "N", description = "Normal force of wheel w on panel j"]
        tau::Mat{nw,nd - 1}, [unit = "N", description = "Traction of wheel w on panel j"]
        Gx::Mat{nw,nd - 1}, [unit = "N", description = "Force on wheel w from panel j, x"]
        Gy::Mat{nw,nd - 1}, [unit = "N", description = "Force on wheel w from panel j, y"]
        Sx::Mat{nw,nd - 1}, [unit = "N", description = "Running sum of Gx over the panels"]
        Sy::Mat{nw,nd - 1}, [unit = "N", description = "Running sum of Gy over the panels"]
        Sf::Mat{nw,nd - 1}, [unit = "N", description = "Running sum of fc over the panels"]
        Sd::Mat{nw,nd - 1}, [unit = "m", description = "Running sum of on * del over the panels"]
        Ax::Mat{nw,nd - 1}, [unit = "N", description = "Running sum over the wheels of (1 - xi) Gx (panel start node)"]
        Ay::Mat{nw,nd - 1}, [unit = "N", description = "Running sum over the wheels of (1 - xi) Gy"]
        Bx::Mat{nw,nd - 1}, [unit = "N", description = "Running sum over the wheels of xi Gx (panel end node)"]
        By::Mat{nw,nd - 1}, [unit = "N", description = "Running sum over the wheels of xi Gy"]
        fbx::Vec{nw}, [unit = "N", description = "Wheel force in the body frame, x"]
        fby::Vec{nw}, [unit = "N", description = "Wheel force in the body frame, y"]
        Wt::Vec{nw}, [unit = "N*m", description = "Running sum of the wheel moments about the body origin"]
        Wx::Vec{nw}, [unit = "N", description = "Running sum of fbx"]
        Wy::Vec{nw}, [unit = "N", description = "Running sum of fby"]

    end
    @outputs begin
        Fx::Vec{nn}, [unit = "N"]
        Fy::Vec{nn}, [unit = "N"]
        fn::Vec{nw}, [unit = "N"]
        delta::Vec{nw}, [unit = "m"]
        s::Vec{nw}, [unit = "m"]
    end
    @equations begin
        ct ~ cos(g[1])
        st ~ sin(g[1])
        for j in 1:(nd - 1)
            Ls[j] ~ sqrt((x[j + 1] - x[j]) * (x[j + 1] - x[j]) + (y[j + 1] - y[j]) * (y[j + 1] - y[j]))
            tx[j] ~ (x[j + 1] - x[j]) / Ls[j]
            ty[j] ~ (y[j + 1] - y[j]) / Ls[j]
        end
        for w in 1:nw
            cx[w] ~ g[2] + ct * rx[w] - st * ry[w]
            cy[w] ~ g[3] + st * rx[w] + ct * ry[w]
            vcx[w] ~ ct * (p.f[2] - p.f[1] * ry[w]) - st * (p.f[3] + p.f[1] * rx[w])
            vcy[w] ~ st * (p.f[2] - p.f[1] * ry[w]) + ct * (p.f[3] + p.f[1] * rx[w])
            for j in 1:(nd - 1)
                xi[w, j] ~ ((cx[w] - x[j]) * tx[j] + (cy[w] - y[j]) * ty[j]) / Ls[j]
                xc[w, j] ~ min(max(xi[w, j], 0.0), 1.0)
                # the convex combination puts a clamped end exactly on the node (no round-off),
                # so two panels meeting at a crest give bit-identical deflections there
                dx[w, j] ~ cx[w] - ((1 - xc[w, j]) * x[j] + xc[w, j] * x[j + 1])
                dy[w, j] ~ cy[w] - ((1 - xc[w, j]) * y[j] + xc[w, j] * y[j + 1])
                dist[w, j] ~ sqrt(dx[w, j] * dx[w, j] + dy[w, j] * dy[w, j])
                nx[w, j] ~ dx[w, j] / dist[w, j]
                ny[w, j] ~ dy[w, j] / dist[w, j]
                del[w, j] ~ r - dist[w, j]
                deld[w, j] ~ -nx[w, j] * (vcx[w] - (1 - xc[w, j]) * xd[j] - xc[w, j] * xd[j + 1]) -
                             ny[w, j] * (vcy[w] - (1 - xc[w, j]) * yd[j] - xc[w, j] * yd[j + 1])
                on[w, j] ~ ifelse((del[w, j] > 0) && (bs[w, j] >= 0) && (bs[w, j + 1] < 0), 1.0, 0.0)
                fc[w, j] ~ on[w, j] * del[w, j] * (k + c * deld[w, j] / dref)
                tau[w, j] ~ on[w, j] * Fd / nw
                Gx[w, j] ~ fc[w, j] * nx[w, j] + tau[w, j] * tx[j]
                Gy[w, j] ~ fc[w, j] * ny[w, j] + tau[w, j] * ty[j]
            end
            bs[w, 1] ~ r
            for i in 2:(nd - 1)
                bs[w, i] ~ (cx[w] - x[i]) * (tx[i - 1] + tx[i]) + (cy[w] - y[i]) * (ty[i - 1] + ty[i])
            end
            bs[w, nd] ~ -r
            Sx[w, 1] ~ Gx[w, 1]
            Sy[w, 1] ~ Gy[w, 1]
            Sf[w, 1] ~ fc[w, 1]
            Sd[w, 1] ~ on[w, 1] * del[w, 1]
            for j in 2:(nd - 1)
                Sx[w, j] ~ Sx[w, j - 1] + Gx[w, j]
                Sy[w, j] ~ Sy[w, j - 1] + Gy[w, j]
                Sf[w, j] ~ Sf[w, j - 1] + fc[w, j]
                Sd[w, j] ~ Sd[w, j - 1] + on[w, j] * del[w, j]
            end
            fn[w] ~ Sf[w, nd - 1]
            delta[w] ~ Sd[w, nd - 1]
            s[w] ~ cx[w]
            fbx[w] ~ ct * Sx[w, nd - 1] + st * Sy[w, nd - 1]
            fby[w] ~ -st * Sx[w, nd - 1] + ct * Sy[w, nd - 1]
        end
        Wt[1] ~ rx[1] * fby[1] - ry[1] * fbx[1]
        Wx[1] ~ fbx[1]
        Wy[1] ~ fby[1]
        for w in 2:nw
            Wt[w] ~ Wt[w - 1] + rx[w] * fby[w] - ry[w] * fbx[w]
            Wx[w] ~ Wx[w - 1] + fbx[w]
            Wy[w] ~ Wy[w - 1] + fby[w]
        end
        p.e[1] ~ -Wt[nw]
        p.e[2] ~ -Wx[nw]
        p.e[3] ~ -Wy[nw]
        for j in 1:(nd - 1)
            Ax[1, j] ~ (1 - xc[1, j]) * Gx[1, j]
            Ay[1, j] ~ (1 - xc[1, j]) * Gy[1, j]
            Bx[1, j] ~ xc[1, j] * Gx[1, j]
            By[1, j] ~ xc[1, j] * Gy[1, j]
            for w in 2:nw
                Ax[w, j] ~ Ax[w - 1, j] + (1 - xc[w, j]) * Gx[w, j]
                Ay[w, j] ~ Ay[w - 1, j] + (1 - xc[w, j]) * Gy[w, j]
                Bx[w, j] ~ Bx[w - 1, j] + xc[w, j] * Gx[w, j]
                By[w, j] ~ By[w - 1, j] + xc[w, j] * Gy[w, j]
            end
        end
        Fx[1] ~ -Ax[nw, 1]
        Fy[1] ~ -Ay[nw, 1]
        for i in 2:(nd - 1)
            Fx[i] ~ -Ax[nw, i] - Bx[nw, i - 1]
            Fy[i] ~ -Ay[nw, i] - By[nw, i - 1]
        end
        Fx[nd] ~ -Bx[nw, nd - 1]
        Fy[nd] ~ -By[nw, nd - 1]
        for i in (nd + 1):nn
            Fx[i] ~ 0.0
            Fy[i] ~ 0.0
        end
    end
    @causality p => (:effort_out, :fixed)
end
