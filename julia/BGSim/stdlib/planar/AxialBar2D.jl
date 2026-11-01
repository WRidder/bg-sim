@block AxialBar2D begin
    # Axial two-force member between two pin nodes (the atomic core of `Bar2D`): a nonlinear
    # C (axial spring EA/L0) and R (stiffness-proportional damping) on the bar elongation,
    # with brittle failure by events.
    #
    # Co-rotational (geometrically exact) kinematics: the length is the distance between the
    # node positions read from the poses `ga`, `gb` (any rotation of the bar is exact), the
    # unit vector n = (xb - xa)/L, and the elongation rate n . (vb - va) from the port flows.
    # The elongation `e` is the integral of that rate from 0, so the bar is unstressed at the
    # node positions of t = 0 and its rest length is L0 = L - e (the "length from the node
    # positions"). Axial force, tension positive:
    #
    #     N = (1 - broken) EA/L0 (e + beta de/dt)
    #
    # The force on node A is +N n, on node B -N n; the port efforts are the forces the nodes
    # exert on the bar, so the port power is N de/dt = dEe/dt + beta-dissipation (power
    # continuous, no torque at the pins).
    #
    # Failure (events, a held flag `ddt(broken) ~ 0` set by `reinit`):
    #   * tension: N rises above the strength Ft = fy A (yield / fracture);
    #   * compression: -N rises above the Euler load Pcr = pi^2 E I / (K L0)^2 (buckling).
    # Either way the bar FAILS: from then on it carries no force (an elastic-brittle model;
    # the post-buckling plateau of a real strut is not modelled). The strain energy it held
    # at that instant leaves the structure and is booked in `Elost`.
    #
    # `util` is the signed utilisation: N/Ft in tension (0..1), N/Pcr in compression (-1..0).
    @ports begin
        pa::Power{Planar}, [frame = "world"]
        pb::Power{Planar}, [frame = "world"]
    end
    @inputs begin
        ga::Vec{3}, [description = "Pose (theta, x, y) of node A"]
        gb::Vec{3}, [description = "Pose (theta, x, y) of node B"]
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
    @variables begin
        e::Real = 0.0, [unit = "m", state = :prefer, description = "Elongation from the length at t = 0"]
        broken::Real = 0.0, [unit = "1", description = "Failure flag: 0 intact, 1 failed (held)"]
        Elost::Real = 0.0, [unit = "J", description = "Strain energy released when the bar failed"]
        Ed::Real = 0.0, [unit = "J", description = "Energy dissipated by the bar damping"]
        dx::Real = 1.0, [unit = "m", description = "xb - xa"]
        dy::Real = 0.0, [unit = "m", description = "yb - ya"]
        nx::Real = 1.0, [unit = "1", description = "Unit vector A to B, x"]
        ny::Real = 0.0, [unit = "1", description = "Unit vector A to B, y"]
        Ld::Real = 0.0, [unit = "m/s", description = "Elongation rate"]
        L0::Real = 1.0, [unit = "m", description = "Rest length L - e"]
        k::Real = 1.0, [unit = "N/m", description = "Axial stiffness EA/L0"]
        Ne::Real = 0.0, [unit = "N", description = "Elastic part of the axial force"]
        Nd::Real = 0.0, [unit = "N", description = "Damping part of the axial force"]
        Nu::Real = 0.0, [unit = "N", description = "Force the bar would carry intact (the sign of util)"]
    end
    @outputs begin
        N::Real, [unit = "N"]
        util::Real, [unit = "1"]
        brokenout::Real, [unit = "1"]
        L::Real, [unit = "m"]
        Ft::Real, [unit = "N"]
        Pcr::Real, [unit = "N"]
        m::Real, [unit = "kg"]
        Ee::Real, [unit = "J"]
        Pd::Real, [unit = "W"]
        Edis::Real, [unit = "J"]
        Elostout::Real, [unit = "J"]
    end
    @equations begin
        dx ~ gb[2] - ga[2]
        dy ~ gb[3] - ga[3]
        L ~ sqrt(dx * dx + dy * dy)
        nx ~ dx / L
        ny ~ dy / L
        Ld ~ nx * (pb.f[2] - pa.f[2]) + ny * (pb.f[3] - pa.f[3])
        ddt(e) ~ Ld
        L0 ~ L - e
        k ~ E * A / L0
        Ne ~ (1 - broken) * k * e
        Nd ~ (1 - broken) * k * beta * Ld
        N ~ Ne + Nd
        ddt(broken) ~ 0.0
        ddt(Elost) ~ 0.0
        pa.e[1] ~ 0.0
        pa.e[2] ~ -N * nx
        pa.e[3] ~ -N * ny
        pb.e[1] ~ 0.0
        pb.e[2] ~ N * nx
        pb.e[3] ~ N * ny
        Ft ~ fy * A
        Pcr ~ 9.869604401089358 * E * I / (K * K * L0 * L0)
        # the switch reads the intact force: N of a failed bar is identically zero, and a
        # switching condition that never leaves zero can trap the event root finder
        Nu ~ k * (e + beta * Ld)
        util ~ (1 - broken) * ifelse(Nu > 0, Nu / Ft, Nu / Pcr)
        brokenout ~ broken
        m ~ rho * A * L0
        Ee ~ 0.5 * Ne * e
        Pd ~ Nd * Ld
        ddt(Ed) ~ Pd
        Edis ~ Ed
        Elostout ~ Elost
    end
    @events begin
        N > Ft => begin
            reinit(Elost, Elost + 0.5 * (1 - broken) * E * A * e * e / L0)
            reinit(broken, 1.0)
        end
        -N > Pcr => begin
            reinit(Elost, Elost + 0.5 * (1 - broken) * E * A * e * e / L0)
            reinit(broken, 1.0)
        end
    end
    @causality begin
        pa => :effort_out
        pb => :effort_out
    end
end
