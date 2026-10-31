@block MovingPlaneContact begin
    # Compliant contact of a sphere (or a point, r = 0) on a spatial body against a FINITE plane
    # face that MOVES: the face is carried in pure translation by a prescribed carrier (a
    # robot flange, a gantry carriage, a conveyor) and slides on the carrier along an axis
    # driven through a Translation port (a gripper jaw on its guide, a pusher, a press ram).
    # It is the two-body sibling of `ContactPoint` (J-MB13): the same smooth Hunt-Crossley
    # normal law, an ISOTROPIC regularised Coulomb friction and the same spatial port
    # convention, so a body can touch a fixed plane (`ContactPoint`) and moving faces with the
    # same parameters.
    #
    # Mounting (causality), exactly as `ContactPoint`: `FixedTransform3DNeutral` with the
    # CONTACT on side `a` and the body on side `b`; the mount pose is the body pose in the
    # sphere-centre frame (identity when the port frame is the body frame at the centre of a
    # ball). `p.f` is then the NEGATIVE centre twist and `p.e` the wrench on the body in the
    # centre frame, so `e . f` is the power the contact absorbs from the body.
    #
    # Geometry (carrier frame axes = world axes, the carrier translates only): the face at
    # slide position `xs` has its centre at `O = pc + o + a xs` and the outward unit normal `n`
    # (the side the body is on); `t1` is the given tangent projected onto the plane and
    # normalised, `t2 = n x t1` (right-handed `t1, t2, n`), and the face is the rectangle
    # `|u1| <= w1, |u2| <= w2` around `O` (`u_i = t_i . (c - O)` for the sphere centre `c`). The
    # face velocity is `vp = vc + a j.f` (carrier velocity plus the slide rate).
    #
    # Normal force (no events, no `max`; the same law and smoothing as `ContactPoint`):
    #   h     = n . (c - O)                     height of the centre above the plane
    #   d     = r - h                           penetration of the sphere (positive = inside)
    #   x     = (d + sqrt(d^2 + eps^2)) / 2     smooth positive part (sigma = dx/dd)
    #   xdot  = sigma d/dt(d) = -sigma n . (v - vp)
    #   Fx    = k x (x/xref)^(1/2) (1 + c xdot)  Hunt-Crossley, Hertz exponent 3/2
    #   Fc    = (Fx + sqrt(Fx^2 + feps^2)) / 2   smooth no-pull clamp
    #   f_n   = G sigma Fc                       G = smooth edge gate of the finite face
    # The gate is `G = q1 q2`, `q_i = (1 + tanh((w_i - u_i)/we)) (1 + tanh((w_i + u_i)/we)) / 4`:
    # 1 on the face, 0 beyond its edges, with a transition of width ~ `we`. The gate scales the
    # spring force only, so a body that slides over an edge while pressed loses a little
    # spring energy (the tangential gradient of `G Ec` is not applied); `Pd` counts it.
    #
    # Friction (isotropic regularised Coulomb, at the contact point P = c - r n):
    #   u     = v + w x (P - c) - vp             slip velocity of the material point of the body
    #   s_i   = t_i . u,  S = sqrt(s1^2 + s2^2 + (vs/100)^2)
    #   F_ti  = mu f_n tanh(S/vs) s_i / S        acting against the slip
    # so |F_t| <= mu f_n in every direction (the two scalar dampers of `ContactPoint` allow up to
    # sqrt(2) mu f_n along a diagonal, which would overstate a friction grip). A stuck contact
    # creeps at `|s| ~ vs atanh(|F_t| / (mu f_n))`, the regularisation error.
    #
    # Forces: the world force on the body `F = f_n n - F_t1 t1 - F_t2 t2` acts at P, so the torque
    # about the centre is `(P - c) x F = r (F_t1 t2 - F_t2 t1)`. The port effort is the wrench on
    # the body in the centre frame `[R^T tau; R^T F]`. The face is massless: the slide port carries
    # `j.e = F . a` (the force the slide drive must supply along the axis), and the carrier
    # takes the rest. Power: `p.e . p.f + j.e j.f + Pc = (storage + dissipation)`, with
    # `Pc = F . vc` the power the prescribed carrier delivers (an MSf in bond-graph terms).
    #
    # The slide drive train is modelled in the carrier frame: the carrier acceleration along the
    # slide axis is not applied to it (place the slide perpendicular to the carrier motion, or
    # add an MSe with the inertial force).
    @ports begin
        p::Power{Spatial}
        j::Power{Translation}
    end
    @inputs begin
        g::Vec{7}, [description = "World pose of the sphere centre (D-MB6 chart)"]
        pc::Vec{3}, [unit = "m", description = "Carrier origin in the world"]
        vc::Vec{3}, [unit = "m/s", description = "Carrier velocity in the world"]
        xs::Real, [unit = "m", description = "Slide position of the face along the slide axis (a PositionSensor on the node of j)"]
    end
    @outputs begin
        f_n::Real, [unit = "N", description = "Normal contact force on the body (>= 0)"]
        delta::Real, [unit = "m", description = "Signed penetration of the sphere (positive = inside the face)"]
        s1::Real, [unit = "m/s", description = "Slip velocity along tangent 1"]
        s2::Real, [unit = "m/s", description = "Slip velocity along tangent 2"]
        slip::Real, [unit = "m/s", description = "Slip speed |s|"]
        ft::Real, [unit = "N", description = "Friction force magnitude"]
        util::Real, [unit = "1", description = "Friction utilisation |F_t| / (mu f_n): 1 when sliding"]
        u1::Real, [unit = "m", description = "Contact point on the face along tangent 1 (from the face centre)"]
        u2::Real, [unit = "m", description = "Contact point on the face along tangent 2 (from the face centre)"]
        gate::Real, [unit = "1", description = "Edge gate: 1 on the face, 0 off it"]
        F::Vec{3}, [unit = "N", description = "World force on the body (normal plus friction)"]
        Ec::Real, [unit = "J", description = "Energy stored in the normal spring (ungated)"]
        Pd::Real, [unit = "W", description = "Dissipated power (normal damping, friction, edge gate)"]
        Pc::Real, [unit = "W", description = "Power delivered by the prescribed carrier, F . vc"]
    end
    @parameters begin
        r::Real = 0.0, [unit = "m", min = 0, description = "Sphere radius (0 = a point contact)"]
        ox::Real = 0.0, [unit = "m", description = "Face centre x in the carrier frame at xs = 0"]
        oy::Real = 0.0, [unit = "m", description = "Face centre y in the carrier frame at xs = 0"]
        oz::Real = 0.0, [unit = "m", description = "Face centre z in the carrier frame at xs = 0"]
        nx::Real = 0.0, [unit = "1", description = "Outward face normal x (towards the body; normalised internally)"]
        ny::Real = 0.0, [unit = "1", description = "Outward face normal y"]
        nz::Real = 1.0, [unit = "1", description = "Outward face normal z"]
        tx::Real = 1.0, [unit = "1", description = "Tangent 1 direction x (projected onto the face and normalised)"]
        ty::Real = 0.0, [unit = "1", description = "Tangent 1 direction y"]
        tz::Real = 0.0, [unit = "1", description = "Tangent 1 direction z"]
        ax::Real = 0.0, [unit = "1", description = "Slide axis x (normalised internally; positive j.f moves the face along it)"]
        ay::Real = 0.0, [unit = "1", description = "Slide axis y"]
        az::Real = 1.0, [unit = "1", description = "Slide axis z"]
        w1::Real = 1.0e3, [unit = "m", min = 0, description = "Half-width of the face along tangent 1"]
        w2::Real = 1.0e3, [unit = "m", min = 0, description = "Half-width of the face along tangent 2"]
        we::Real = 5.0e-4, [unit = "m", min = 1.0e-12, description = "Edge smoothing length of the face"]
        k::Real = 1.0e4, [unit = "N/m", min = 0, description = "Contact stiffness: force = k x (x/xref)^(1/2) with x in m (Hertz, exponent 3/2)"]
        xref::Real = 1.0e-3, [unit = "m", min = 1.0e-12, description = "Reference penetration that makes the 3/2 power unit-clean (force = k xref at x = xref)"]
        c::Real = 1.0, [unit = "s/m", min = 0, description = "Hunt-Crossley damping coefficient: force = Fk (1 + c xdot)"]
        mu::Real = 0.5, [unit = "1", min = 0, description = "Coulomb friction coefficient"]
        vs::Real = 1.0e-3, [unit = "m/s", min = 1.0e-12, description = "Friction regularisation velocity (tanh(|s|/vs))"]
        eps::Real = 1.0e-6, [unit = "m", min = 0, description = "Smoothing length of the penetration positive part"]
        feps::Real = 1.0e-6, [unit = "N", min = 0, description = "Smoothing force of the no-pull clamp"]
    end
    @variables begin
        sq::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the centre frame in the world"]
        nn::Real = 1.0, [unit = "1", description = "Length of the normal parameter vector"]
        n1::Real = 0.0, [unit = "1", description = "Unit normal x"]
        n2::Real = 0.0, [unit = "1", description = "Unit normal y"]
        n3::Real = 1.0, [unit = "1", description = "Unit normal z"]
        an::Real = 1.0, [unit = "1", description = "Length of the slide axis parameter vector"]
        e1::Real = 0.0, [unit = "1", description = "Unit slide axis x"]
        e2::Real = 0.0, [unit = "1", description = "Unit slide axis y"]
        e3::Real = 1.0, [unit = "1", description = "Unit slide axis z"]
        tn::Real = 1.0, [unit = "1", description = "Tangent dot normal"]
        tl::Real = 1.0, [unit = "1", description = "Length of the projected tangent"]
        t11::Real = 1.0, [unit = "1", description = "Tangent 1 x"]
        t12::Real = 0.0, [unit = "1", description = "Tangent 1 y"]
        t13::Real = 0.0, [unit = "1", description = "Tangent 1 z"]
        t21::Real = 0.0, [unit = "1", description = "Tangent 2 x (n x t1)"]
        t22::Real = 1.0, [unit = "1", description = "Tangent 2 y"]
        t23::Real = 0.0, [unit = "1", description = "Tangent 2 z"]
        v1::Real = 0.0, [unit = "m/s", description = "Centre velocity, world x"]
        v2::Real = 0.0, [unit = "m/s", description = "Centre velocity, world y"]
        v3::Real = 0.0, [unit = "m/s", description = "Centre velocity, world z"]
        om1::Real = 0.0, [unit = "rad/s", description = "Body angular velocity, world x"]
        om2::Real = 0.0, [unit = "rad/s", description = "Body angular velocity, world y"]
        om3::Real = 0.0, [unit = "rad/s", description = "Body angular velocity, world z"]
        d1::Real = 0.0, [unit = "m", description = "Centre relative to the face centre, world x"]
        d2::Real = 0.0, [unit = "m", description = "Centre relative to the face centre, world y"]
        d3::Real = 0.0, [unit = "m", description = "Centre relative to the face centre, world z"]
        vp1::Real = 0.0, [unit = "m/s", description = "Face velocity, world x"]
        vp2::Real = 0.0, [unit = "m/s", description = "Face velocity, world y"]
        vp3::Real = 0.0, [unit = "m/s", description = "Face velocity, world z"]
        h::Real = 0.0, [unit = "m", description = "Height of the centre above the plane"]
        rr::Real = 1.0e-6, [unit = "m", description = "sqrt(delta^2 + eps^2)"]
        x::Real = 1.0e-3, [unit = "m", description = "Smooth positive penetration"]
        sig::Real = 0.5, [unit = "1", description = "dx/d(delta)"]
        xd::Real = 0.0, [unit = "m/s", description = "Rate of the smooth penetration"]
        q1::Real = 1.0, [unit = "1", description = "Edge gate along tangent 1"]
        q2::Real = 1.0, [unit = "1", description = "Edge gate along tangent 2"]
        xe::Real = 1.0e-4, [unit = "m", description = "x (x/xref)^(1/2)"]
        Fk::Real = 1.0, [unit = "N", description = "Spring force k x (x/xref)^(1/2)"]
        Fx::Real = 1.0, [unit = "N", description = "Hunt-Crossley force Fk (1 + c xd)"]
        Fc::Real = 1.0, [unit = "N", description = "Clamped Hunt-Crossley force"]
        us1::Real = 0.0, [unit = "m/s", description = "Slip velocity of the contact point, world x"]
        us2::Real = 0.0, [unit = "m/s", description = "Slip velocity of the contact point, world y"]
        us3::Real = 0.0, [unit = "m/s", description = "Slip velocity of the contact point, world z"]
        sm::Real = 1.0e-5, [unit = "m/s", description = "Smoothed slip speed sqrt(s1^2 + s2^2 + (vs/100)^2)"]
        qf::Real = 0.0, [unit = "N*s/m", description = "Friction factor mu f_n tanh(sm/vs)/sm"]
        ft1::Real = 0.0, [unit = "N", description = "Friction force along tangent 1 (acts against s1)"]
        ft2::Real = 0.0, [unit = "N", description = "Friction force along tangent 2 (acts against s2)"]
        tq1::Real = 0.0, [unit = "N*m", description = "Torque on the body about the centre, world x"]
        tq2::Real = 0.0, [unit = "N*m", description = "Torque on the body about the centre, world y"]
        tq3::Real = 0.0, [unit = "N*m", description = "Torque on the body about the centre, world z"]
    end
    @equations begin
        sq ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / sq
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / sq
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / sq
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / sq
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / sq
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / sq
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / sq
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / sq
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / sq
        # Face frame: unit normal, unit slide axis, t1 = the tangent parameter projected onto the
        # plane, t2 = n x t1.
        nn ~ sqrt(nx * nx + ny * ny + nz * nz)
        n1 ~ nx / nn
        n2 ~ ny / nn
        n3 ~ nz / nn
        an ~ sqrt(ax * ax + ay * ay + az * az)
        e1 ~ ax / an
        e2 ~ ay / an
        e3 ~ az / an
        tn ~ tx * n1 + ty * n2 + tz * n3
        tl ~ sqrt((tx - tn * n1)^2 + (ty - tn * n2)^2 + (tz - tn * n3)^2)
        t11 ~ (tx - tn * n1) / tl
        t12 ~ (ty - tn * n2) / tl
        t13 ~ (tz - tn * n3) / tl
        t21 ~ n2 * t13 - n3 * t12
        t22 ~ n3 * t11 - n1 * t13
        t23 ~ n1 * t12 - n2 * t11
        # Body motion in the world: the port flow is the NEGATIVE centre twist (mount side a).
        om1 ~ -(R[1, 1] * p.f[1] + R[1, 2] * p.f[2] + R[1, 3] * p.f[3])
        om2 ~ -(R[2, 1] * p.f[1] + R[2, 2] * p.f[2] + R[2, 3] * p.f[3])
        om3 ~ -(R[3, 1] * p.f[1] + R[3, 2] * p.f[2] + R[3, 3] * p.f[3])
        v1 ~ -(R[1, 1] * p.f[4] + R[1, 2] * p.f[5] + R[1, 3] * p.f[6])
        v2 ~ -(R[2, 1] * p.f[4] + R[2, 2] * p.f[5] + R[2, 3] * p.f[6])
        v3 ~ -(R[3, 1] * p.f[4] + R[3, 2] * p.f[5] + R[3, 3] * p.f[6])
        # Face pose and velocity: carried by the carrier, slid along the axis.
        d1 ~ g[5] - (pc[1] + ox + e1 * xs)
        d2 ~ g[6] - (pc[2] + oy + e2 * xs)
        d3 ~ g[7] - (pc[3] + oz + e3 * xs)
        vp1 ~ vc[1] + e1 * j.f
        vp2 ~ vc[2] + e2 * j.f
        vp3 ~ vc[3] + e3 * j.f
        # Normal law (ContactPoint's, for a sphere of radius r).
        h ~ n1 * d1 + n2 * d2 + n3 * d3
        delta ~ r - h
        rr ~ sqrt(delta * delta + eps * eps)
        x ~ 0.5 * eps * eps / (rr - delta)
        sig ~ x / rr
        xd ~ -sig * (n1 * (v1 - vp1) + n2 * (v2 - vp2) + n3 * (v3 - vp3))
        u1 ~ t11 * d1 + t12 * d2 + t13 * d3
        u2 ~ t21 * d1 + t22 * d2 + t23 * d3
        q1 ~ 0.25 * (1 + tanh((w1 - u1) / we)) * (1 + tanh((w1 + u1) / we))
        q2 ~ 0.25 * (1 + tanh((w2 - u2) / we)) * (1 + tanh((w2 + u2) / we))
        gate ~ q1 * q2
        xe ~ x * sqrt(x / xref)
        Fk ~ k * xe
        Fx ~ Fk * (1 + c * xd)
        Fc ~ 0.5 * (Fx + sqrt(Fx * Fx + feps * feps))
        f_n ~ gate * sig * Fc
        Ec ~ 0.4 * k * xe * x
        # Slip of the body's material point at P = c - r n against the face: u = v - r (w x n) - vp.
        us1 ~ v1 - r * (om2 * n3 - om3 * n2) - vp1
        us2 ~ v2 - r * (om3 * n1 - om1 * n3) - vp2
        us3 ~ v3 - r * (om1 * n2 - om2 * n1) - vp3
        s1 ~ t11 * us1 + t12 * us2 + t13 * us3
        s2 ~ t21 * us1 + t22 * us2 + t23 * us3
        sm ~ sqrt(s1 * s1 + s2 * s2 + 1.0e-4 * vs * vs)
        qf ~ mu * f_n * tanh(sm / vs) / sm
        ft1 ~ qf * s1
        ft2 ~ qf * s2
        slip ~ sqrt(s1 * s1 + s2 * s2)
        ft ~ qf * slip
        util ~ ft / (mu * f_n + feps)
        F[1] ~ f_n * n1 - ft1 * t11 - ft2 * t21
        F[2] ~ f_n * n2 - ft1 * t12 - ft2 * t22
        F[3] ~ f_n * n3 - ft1 * t13 - ft2 * t23
        tq1 ~ r * (ft1 * t21 - ft2 * t11)
        tq2 ~ r * (ft1 * t22 - ft2 * t12)
        tq3 ~ r * (ft1 * t23 - ft2 * t13)
        Pd ~ gate * (Fc - Fk) * xd + ft1 * s1 + ft2 * s2
        Pc ~ F[1] * vc[1] + F[2] * vc[2] + F[3] * vc[3]
        # Port efforts: the wrench on the body in the centre frame, and the slide force.
        p.e[1] ~ R[1, 1] * tq1 + R[2, 1] * tq2 + R[3, 1] * tq3
        p.e[2] ~ R[1, 2] * tq1 + R[2, 2] * tq2 + R[3, 2] * tq3
        p.e[3] ~ R[1, 3] * tq1 + R[2, 3] * tq2 + R[3, 3] * tq3
        p.e[4] ~ R[1, 1] * F[1] + R[2, 1] * F[2] + R[3, 1] * F[3]
        p.e[5] ~ R[1, 2] * F[1] + R[2, 2] * F[2] + R[3, 2] * F[3]
        p.e[6] ~ R[1, 3] * F[1] + R[2, 3] * F[2] + R[3, 3] * F[3]
        j.e ~ F[1] * e1 + F[2] * e2 + F[3] * e3
    end
    @causality begin
        p => (:effort_out, :fixed)
        j => (:effort_out, :fixed)
    end
end
