@block BeaverWrench begin
    # The wrench of the air and the engine on the Beaver, as the six inputs of
    # `stdlib:multibond/ExternalWrenchSpatial` in the geometric body frame (x forward, y left, z up,
    # about the centre of gravity). The coefficients come from BeaverAero and BeaverPropulsion
    # (body axes FRD, as the source):
    #
    #   X = qd S (CXa + CXp),  Y = qd S (CYa + CYp),  Z = qd S (CZa + CZp)
    #   L = qd S b (Cla + Clp),  M = qd S c (Cma + Cmp),  N = qd S b (Cna + Cnp)
    #
    # Two corrections make the rigid body (uniform gravity g0) follow the FDC equations exactly:
    #
    #   * gravity: FDC uses g(H) = 9.80665 (6371020/(6371020 + H))^2, the body's own weight uses g0;
    #     the difference m (g - g0) acts along the local vertical.
    #   * the beta-dot term of the side force (CYbdot bdot b/2V): FDC leaves it out of the force and
    #     divides the beta-dot equation by 1 - k, k = cos(beta) rho b S CYbdot/(4 m) (block xdotcorr;
    #     V-dot and alpha-dot are not corrected). Here the force m V bdot0 k/(1 - k) acts along
    #     e_beta = (-cos(alpha) sin(beta), cos(beta), -sin(alpha) sin(beta)) (FRD), the direction
    #     that changes beta only (orthogonal to the velocity and to the alpha direction), with
    #     bdot0 the uncorrected beta-dot from the other forces. Then beta-dot = bdot0/(1 - k).
    #
    # nz, ny are the load factors -Z/(m g), Y/(m g) of the air and engine forces.
    @inputs begin
        CXa::Real
        CYa::Real
        CZa::Real
        Cla::Real
        Cma::Real
        Cna::Real
        CXp::Real
        CYp::Real
        CZp::Real
        Clp::Real
        Cmp::Real
        Cnp::Real
        V::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
        beta::Real, [unit = "rad"]
        p::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        theta::Real, [unit = "rad"]
        phi::Real, [unit = "rad"]
        rho::Real, [unit = "kg/m^3"]
        g::Real, [unit = "m/s^2"]
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        X::Real, [unit = "N", description = "Air and engine force, x (FRD)"]
        Y::Real, [unit = "N", description = "Air and engine force, y (FRD)"]
        Z::Real, [unit = "N", description = "Air and engine force, z (FRD)"]
        L::Real, [unit = "N*m", description = "Rolling moment (FRD)"]
        M::Real, [unit = "N*m", description = "Pitching moment (FRD)"]
        N::Real, [unit = "N*m", description = "Yawing moment (FRD)"]
        bdot::Real, [unit = "rad/s", description = "Corrected sideslip rate bdot0/(1 - k)"]
        nz::Real
        ny::Real
    end
    @parameters begin
        S::Real = 23.23, [unit = "m^2", description = "Wing area"]
        b::Real = 14.63, [unit = "m", description = "Span"]
        c::Real = 1.5875, [unit = "m", description = "Mean aerodynamic chord"]
        m::Real = 2288.231, [unit = "kg", description = "Mass"]
        g0::Real = 9.80665, [unit = "m/s^2", description = "Gravity of the rigid body"]
        CYbdot::Real = -0.16, [description = "Side force due to the sideslip rate"]
    end
    @variables begin
        qd::Real = 0.0, [unit = "Pa"]
        Gx::Real = 0.0
        Gy::Real = 0.0
        Gz::Real = 0.0
        k::Real = 0.0
        bdot0::Real = 0.0
        Fb::Real = 0.0, [unit = "N", description = "beta-dot correction force"]
        Xt::Real = 0.0
        Yt::Real = 0.0
        Zt::Real = 0.0
    end
    @equations begin
        qd ~ 0.5 * rho * V * V
        X ~ qd * S * (CXa + CXp)
        Y ~ qd * S * (CYa + CYp)
        Z ~ qd * S * (CZa + CZp)
        L ~ qd * S * b * (Cla + Clp)
        M ~ qd * S * c * (Cma + Cmp)
        N ~ qd * S * b * (Cna + Cnp)
        # weight with the local gravity, FRD
        Gx ~ -m * g * sin(theta)
        Gy ~ m * g * cos(theta) * sin(phi)
        Gz ~ m * g * cos(theta) * cos(phi)
        bdot0 ~ (-(X + Gx) * cos(alpha) * sin(beta) + (Y + Gy) * cos(beta) - (Z + Gz) * sin(alpha) * sin(beta)) / (m * V) +
                p * sin(alpha) - r * cos(alpha)
        k ~ cos(beta) * rho * b * S * CYbdot / (4.0 * m)
        bdot ~ bdot0 / (1.0 - k)
        Fb ~ m * V * bdot0 * k / (1.0 - k)
        # total external force (FRD) without the rigid body's own weight m g0
        Xt ~ X + (g - g0) * m * (-sin(theta)) + Fb * (-cos(alpha) * sin(beta))
        Yt ~ Y + (g - g0) * m * cos(theta) * sin(phi) + Fb * cos(beta)
        Zt ~ Z + (g - g0) * m * cos(theta) * cos(phi) + Fb * (-sin(alpha) * sin(beta))
        nz ~ -Z / (m * g)
        ny ~ Y / (m * g)
        # FRD -> FLU (y and z change sign)
        fx ~ Xt
        fy ~ -Yt
        fz ~ -Zt
        tx ~ L
        ty ~ -M
        tz ~ -N
    end
end
