@block RollingSphere begin
    # Compliant rolling contact between TWO spatial bodies: a sphere of radius `r` on body `b`
    # (centred at the body origin, e.g. a ball) against a finite plane face fixed in body `a`
    # (a tilting plate, a turntable, a moving tray). Unlike `ContactPoint` and `RollingDisk`
    # (a body against the fixed world plane of a `ContactSurface`) and `MovingPlaneContact` (a
    # face in pure translation), the face here rotates and translates with its body, and the
    # reaction goes back into that body: the element is a two-port C/R multiport between the
    # two body 1-junctions, so the face body feels the ball's weight, the rolling resistance
    # and the friction, and every term of the moving surface (the face's rotation rate and
    # acceleration) enters the ball's motion.
    #
    # Mounting: each body's port (`RigidBody3D.p`, a 1-junction) attaches DIRECTLY to `a`
    # (face body) and `b` (sphere body), as for `RollingDisk`. The port flows are the body
    # twists `[w; v]` (body frames) and the port efforts are minus the contact wrenches on the
    # bodies about their origins, so `a.e . a.f + b.e . b.f` is the power the contact
    # absorbs. `ga` is the world pose of body
    # a's frame, `gb` that of the sphere centre (D-MB6 chart, e.g. `ComposePose3D` or
    # `PoseIntegrator3D` outputs).
    #
    # Geometry (all in the world frame): the face has the origin `O = pa + Ra o` and the unit
    # outward normal `n = Ra m` (`m` the normalised parameter normal, the side the sphere is
    # on), the tangents `t1 = Ra e1` (the parameter tangent projected on the face) and
    # `t2 = n x t1`. For the sphere centre `c`:
    #   h  = n . (c - O),   delta = r - h   (penetration, positive = inside),
    #   u1 = t1 . (c - O),  u2 = t2 . (c - O)   (contact position on the face),
    #   P  = c - r n        (contact point), lever from body a's origin la = P - pa.
    # The relative velocity of the two material points at P is
    #   u  = (vb + wb x (-r n)) - (va + wa x la),
    # and dh/dt = n . u exactly (the face rotation term (wa x n) . (c - O) cancels the lever
    # term), so the normal force does exactly the work d(Ec)/dt of its spring.
    #
    # Normal force: the smooth Hunt-Crossley law of `ContactPoint` (Hertz exponent 3/2,
    # smooth positive part, no-pull clamp, no events), gated by the finite face as in
    # `MovingPlaneContact` (`G = 1` on the face, 0 beyond the half-widths `w1`, `w2`, a
    # transition of width ~`we`): f_n = G sigma Fc along +n on the sphere.
    # Friction (no-slip by regularisation): isotropic regularised Coulomb on the slip
    # s = (s1, s2) = (t1 . u, t2 . u):  F_t = -mu f_n s / sqrt(|s|^2 + vs^2). A ball that
    # rolls under a tangential load F_t creeps at |s| = vs F_t / sqrt((mu f_n)^2 - F_t^2), the
    # regularisation residual (far below 1 mm/s for vs = 1e-3 m/s inside the friction cone).
    # Rolling resistance (an R on the relative rolling rate): with the relative angular
    # velocity wr = wb - wa and its tangential components wr1 = t1 . wr, wr2 = t2 . wr, the
    # torque on the sphere is
    #   T_r = -crr r f_n (wr1 t1 + wr2 t2) / sqrt(wr1^2 + wr2^2 + ws^2) - bsp (n . wr) n
    # (a regularised Coulomb rolling moment `crr r f_n`, crr the dimensionless rolling
    # resistance coefficient, plus an optional spin (drilling) damping about the normal).
    #
    # Wrenches: the force F = f_n n + F_t acts on the sphere at P and -F on body a at P; T_r on
    # the sphere and -T_r on body a. Torques: sphere about its centre (-r n) x F + T_r, body a
    # about its origin la x (-F) - T_r; both rotated into the body frames for the port efforts.
    # On the face (G = 1) the port power equals d(Ec)/dt + Pd with
    #   Pd = (Fc - Fk) xdot + mu f_n |s|^2/sqrt(|s|^2 + vs^2) + crr r f_n |wr_t|^2/sqrt(|wr_t|^2
    #        + ws^2) + bsp (n . wr)^2 >= 0.
    # Off the face the gate scales the spring force only, so a sphere that rolls over an edge
    # loses its (tiny) spring energy; Ec is reported gated.
    @ports begin
        a::Power{Spatial}, [frame = "body"]
        b::Power{Spatial}, [frame = "body"]
    end
    @inputs begin
        ga::Vec{7}, [description = "World pose of body a (the face body), D-MB6 chart"]
        gb::Vec{7}, [description = "World pose of the sphere centre (body b), D-MB6 chart"]
    end
    @outputs begin
        f_n::Real, [unit = "N", description = "Normal contact force on the sphere (>= 0)"]
        delta::Real, [unit = "m", description = "Signed penetration of the sphere (positive = inside the face)"]
        u1::Real, [unit = "m", description = "Sphere centre on the face along tangent 1 (from the face origin)"]
        u2::Real, [unit = "m", description = "Sphere centre on the face along tangent 2 (from the face origin)"]
        gate::Real, [unit = "1", description = "Edge gate: 1 on the face, 0 off it"]
        s1::Real, [unit = "m/s", description = "Slip velocity of the sphere's contact point relative to the face, along tangent 1"]
        s2::Real, [unit = "m/s", description = "Slip velocity along tangent 2"]
        slip::Real, [unit = "m/s", description = "Slip speed |s| (the no-slip residual)"]
        ft1::Real, [unit = "N", description = "Tangential (friction) force on the sphere along tangent 1"]
        ft2::Real, [unit = "N", description = "Tangential (friction) force on the sphere along tangent 2"]
        wr1::Real, [unit = "rad/s", description = "Relative angular velocity sphere - face about tangent 1 (rolling along t2)"]
        wr2::Real, [unit = "rad/s", description = "Relative angular velocity about tangent 2 (rolling along -t1)"]
        wrn::Real, [unit = "rad/s", description = "Relative spin about the face normal"]
        Ec::Real, [unit = "J", description = "Energy stored in the normal spring (gated)"]
        Pd::Real, [unit = "W", description = "Dissipated power (normal damping, friction, rolling resistance, spin damping)"]
    end
    @parameters begin
        r::Real = 0.0127, [unit = "m", min = 0, description = "Sphere radius"]
        ox::Real = 0.0, [unit = "m", description = "Face origin x in body a's frame"]
        oy::Real = 0.0, [unit = "m", description = "Face origin y in body a's frame"]
        oz::Real = 0.0, [unit = "m", description = "Face origin z in body a's frame"]
        nx::Real = 0.0, [unit = "1", description = "Outward face normal x in body a's frame (towards the sphere; normalised internally)"]
        ny::Real = 0.0, [unit = "1", description = "Outward face normal y"]
        nz::Real = 1.0, [unit = "1", description = "Outward face normal z"]
        tx::Real = 1.0, [unit = "1", description = "Tangent 1 direction x in body a's frame (projected onto the face and normalised)"]
        ty::Real = 0.0, [unit = "1", description = "Tangent 1 direction y"]
        tz::Real = 0.0, [unit = "1", description = "Tangent 1 direction z"]
        w1::Real = 1.0e3, [unit = "m", min = 0, description = "Half-width of the face along tangent 1"]
        w2::Real = 1.0e3, [unit = "m", min = 0, description = "Half-width of the face along tangent 2"]
        we::Real = 5.0e-4, [unit = "m", min = 1.0e-12, description = "Edge smoothing length of the face"]
        k::Real = 1.0e5, [unit = "N/m", min = 0, description = "Contact stiffness: force = k x (x/xref)^(1/2) with x in m (Hertz, exponent 3/2)"]
        xref::Real = 1.0e-4, [unit = "m", min = 1.0e-12, description = "Reference penetration of the 3/2 power (force = k xref at x = xref)"]
        c::Real = 1.0, [unit = "s/m", min = 0, description = "Hunt-Crossley damping coefficient: force = Fk (1 + c xdot)"]
        mu::Real = 0.5, [unit = "1", min = 0, description = "Coulomb friction coefficient (isotropic)"]
        vs::Real = 1.0e-3, [unit = "m/s", min = 1.0e-12, description = "Friction regularisation velocity"]
        crr::Real = 0.0, [unit = "1", min = 0, description = "Rolling resistance coefficient: rolling moment crr r f_n"]
        ws::Real = 1.0e-2, [unit = "rad/s", min = 1.0e-12, description = "Regularisation rate of the rolling moment"]
        bsp::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Optional spin (drilling) damping about the face normal"]
        eps::Real = 1.0e-7, [unit = "m", min = 0, description = "Smoothing length of the penetration positive part"]
        feps::Real = 1.0e-6, [unit = "N", min = 0, description = "Smoothing force of the no-pull clamp"]
    end
    @variables begin
        sa::Real = 1.0, [unit = "1", description = "Squared quaternion norm of ga"]
        sb::Real = 1.0, [unit = "1", description = "Squared quaternion norm of gb"]
        Ra::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of body a in the world"]
        Rb::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the sphere body in the world"]
        nn::Real = 1.0, [unit = "1", description = "Length of the normal parameter vector"]
        m::Vec{3} = [0.0, 0.0, 1.0], [unit = "1", description = "Unit face normal in body a's frame"]
        tm::Real = 0.0, [unit = "1", description = "Tangent parameter dot normal"]
        tl::Real = 1.0, [unit = "1", description = "Length of the projected tangent parameter"]
        e1::Vec{3} = [1.0, 0.0, 0.0], [unit = "1", description = "Unit tangent 1 in body a's frame"]
        e2::Vec{3} = [0.0, 1.0, 0.0], [unit = "1", description = "Unit tangent 2 = m x e1 in body a's frame"]
        n::Vec{3} = [0.0, 0.0, 1.0], [unit = "1", description = "Face normal in the world"]
        t1::Vec{3} = [1.0, 0.0, 0.0], [unit = "1", description = "Tangent 1 in the world"]
        t2::Vec{3} = [0.0, 1.0, 0.0], [unit = "1", description = "Tangent 2 in the world"]
        O::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Face origin in the world"]
        dc::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Sphere centre relative to the face origin"]
        h::Real = 0.0, [unit = "m", description = "Height of the sphere centre above the face"]
        la::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Contact point relative to body a's origin"]
        wa::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Angular velocity of body a, world"]
        va::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Velocity of body a's origin, world"]
        wb::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Angular velocity of the sphere, world"]
        vb::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Velocity of the sphere centre, world"]
        ua::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Velocity of the face material point at the contact, world"]
        ub::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Velocity of the sphere material point at the contact, world"]
        uv::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Relative velocity ub - ua"]
        un::Real = 0.0, [unit = "m/s", description = "Normal relative velocity n . u (= dh/dt)"]
        rr::Real = 1.0e-7, [unit = "m", description = "sqrt(delta^2 + eps^2)"]
        x::Real = 1.0e-5, [unit = "m", description = "Smooth positive penetration"]
        sig::Real = 0.5, [unit = "1", description = "dx/d(delta)"]
        xd::Real = 0.0, [unit = "m/s", description = "Rate of the smooth penetration"]
        xe::Real = 1.0e-5, [unit = "m", description = "x (x/xref)^(1/2)"]
        Fk::Real = 1.0, [unit = "N", description = "Spring force k x (x/xref)^(1/2)"]
        Fx::Real = 1.0, [unit = "N", description = "Hunt-Crossley force Fk (1 + c xd)"]
        Fc::Real = 1.0, [unit = "N", description = "Clamped Hunt-Crossley force"]
        qa::Real = 1.0, [unit = "1", description = "Edge gate along tangent 1"]
        qb::Real = 1.0, [unit = "1", description = "Edge gate along tangent 2"]
        Sn::Real = 1.0e-3, [unit = "m/s", description = "sqrt(|s|^2 + vs^2)"]
        cf::Real = 0.0, [unit = "N*s/m", description = "Friction coefficient of the slip, mu f_n / Sn"]
        F::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "World force on the sphere"]
        wr::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Relative angular velocity wb - wa, world"]
        Wn::Real = 1.0e-2, [unit = "rad/s", description = "sqrt(wr1^2 + wr2^2 + ws^2)"]
        cr::Real = 0.0, [unit = "N*m*s/rad", description = "Rolling moment coefficient crr r f_n / Wn"]
        Tr::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Rolling and spin moment on the sphere, world"]
        Tb::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Torque on the sphere about its centre, world"]
        Ta::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Torque on body a about its origin, world"]
    end
    @equations begin
        sa ~ ga[1] * ga[1] + ga[2] * ga[2] + ga[3] * ga[3] + ga[4] * ga[4]
        Ra[1, 1] ~ (ga[1] * ga[1] + ga[2] * ga[2] - ga[3] * ga[3] - ga[4] * ga[4]) / sa
        Ra[1, 2] ~ 2 * (ga[2] * ga[3] - ga[1] * ga[4]) / sa
        Ra[1, 3] ~ 2 * (ga[2] * ga[4] + ga[1] * ga[3]) / sa
        Ra[2, 1] ~ 2 * (ga[2] * ga[3] + ga[1] * ga[4]) / sa
        Ra[2, 2] ~ (ga[1] * ga[1] - ga[2] * ga[2] + ga[3] * ga[3] - ga[4] * ga[4]) / sa
        Ra[2, 3] ~ 2 * (ga[3] * ga[4] - ga[1] * ga[2]) / sa
        Ra[3, 1] ~ 2 * (ga[2] * ga[4] - ga[1] * ga[3]) / sa
        Ra[3, 2] ~ 2 * (ga[3] * ga[4] + ga[1] * ga[2]) / sa
        Ra[3, 3] ~ (ga[1] * ga[1] - ga[2] * ga[2] - ga[3] * ga[3] + ga[4] * ga[4]) / sa
        sb ~ gb[1] * gb[1] + gb[2] * gb[2] + gb[3] * gb[3] + gb[4] * gb[4]
        Rb[1, 1] ~ (gb[1] * gb[1] + gb[2] * gb[2] - gb[3] * gb[3] - gb[4] * gb[4]) / sb
        Rb[1, 2] ~ 2 * (gb[2] * gb[3] - gb[1] * gb[4]) / sb
        Rb[1, 3] ~ 2 * (gb[2] * gb[4] + gb[1] * gb[3]) / sb
        Rb[2, 1] ~ 2 * (gb[2] * gb[3] + gb[1] * gb[4]) / sb
        Rb[2, 2] ~ (gb[1] * gb[1] - gb[2] * gb[2] + gb[3] * gb[3] - gb[4] * gb[4]) / sb
        Rb[2, 3] ~ 2 * (gb[3] * gb[4] - gb[1] * gb[2]) / sb
        Rb[3, 1] ~ 2 * (gb[2] * gb[4] - gb[1] * gb[3]) / sb
        Rb[3, 2] ~ 2 * (gb[3] * gb[4] + gb[1] * gb[2]) / sb
        Rb[3, 3] ~ (gb[1] * gb[1] - gb[2] * gb[2] - gb[3] * gb[3] + gb[4] * gb[4]) / sb
        # Face frame in body a (normal, projected tangent, t2 = m x e1).
        nn ~ sqrt(nx * nx + ny * ny + nz * nz)
        m[1] ~ nx / nn
        m[2] ~ ny / nn
        m[3] ~ nz / nn
        tm ~ tx * m[1] + ty * m[2] + tz * m[3]
        tl ~ sqrt((tx - tm * m[1]) * (tx - tm * m[1]) + (ty - tm * m[2]) * (ty - tm * m[2]) + (tz - tm * m[3]) * (tz - tm * m[3]))
        e1[1] ~ (tx - tm * m[1]) / tl
        e1[2] ~ (ty - tm * m[2]) / tl
        e1[3] ~ (tz - tm * m[3]) / tl
        e2[1] ~ m[2] * e1[3] - m[3] * e1[2]
        e2[2] ~ m[3] * e1[1] - m[1] * e1[3]
        e2[3] ~ m[1] * e1[2] - m[2] * e1[1]
        # Face frame and origin in the world.
        n[1] ~ Ra[1, 1] * m[1] + Ra[1, 2] * m[2] + Ra[1, 3] * m[3]
        n[2] ~ Ra[2, 1] * m[1] + Ra[2, 2] * m[2] + Ra[2, 3] * m[3]
        n[3] ~ Ra[3, 1] * m[1] + Ra[3, 2] * m[2] + Ra[3, 3] * m[3]
        t1[1] ~ Ra[1, 1] * e1[1] + Ra[1, 2] * e1[2] + Ra[1, 3] * e1[3]
        t1[2] ~ Ra[2, 1] * e1[1] + Ra[2, 2] * e1[2] + Ra[2, 3] * e1[3]
        t1[3] ~ Ra[3, 1] * e1[1] + Ra[3, 2] * e1[2] + Ra[3, 3] * e1[3]
        t2[1] ~ Ra[1, 1] * e2[1] + Ra[1, 2] * e2[2] + Ra[1, 3] * e2[3]
        t2[2] ~ Ra[2, 1] * e2[1] + Ra[2, 2] * e2[2] + Ra[2, 3] * e2[3]
        t2[3] ~ Ra[3, 1] * e2[1] + Ra[3, 2] * e2[2] + Ra[3, 3] * e2[3]
        O[1] ~ ga[5] + Ra[1, 1] * ox + Ra[1, 2] * oy + Ra[1, 3] * oz
        O[2] ~ ga[6] + Ra[2, 1] * ox + Ra[2, 2] * oy + Ra[2, 3] * oz
        O[3] ~ ga[7] + Ra[3, 1] * ox + Ra[3, 2] * oy + Ra[3, 3] * oz
        dc[1] ~ gb[5] - O[1]
        dc[2] ~ gb[6] - O[2]
        dc[3] ~ gb[7] - O[3]
        h ~ n[1] * dc[1] + n[2] * dc[2] + n[3] * dc[3]
        delta ~ r - h
        u1 ~ t1[1] * dc[1] + t1[2] * dc[2] + t1[3] * dc[3]
        u2 ~ t2[1] * dc[1] + t2[2] * dc[2] + t2[3] * dc[3]
        la[1] ~ gb[5] - r * n[1] - ga[5]
        la[2] ~ gb[6] - r * n[2] - ga[6]
        la[3] ~ gb[7] - r * n[3] - ga[7]
        # World twists (the port flows are the body twists).
        wa[1] ~ Ra[1, 1] * a.f[1] + Ra[1, 2] * a.f[2] + Ra[1, 3] * a.f[3]
        wa[2] ~ Ra[2, 1] * a.f[1] + Ra[2, 2] * a.f[2] + Ra[2, 3] * a.f[3]
        wa[3] ~ Ra[3, 1] * a.f[1] + Ra[3, 2] * a.f[2] + Ra[3, 3] * a.f[3]
        va[1] ~ Ra[1, 1] * a.f[4] + Ra[1, 2] * a.f[5] + Ra[1, 3] * a.f[6]
        va[2] ~ Ra[2, 1] * a.f[4] + Ra[2, 2] * a.f[5] + Ra[2, 3] * a.f[6]
        va[3] ~ Ra[3, 1] * a.f[4] + Ra[3, 2] * a.f[5] + Ra[3, 3] * a.f[6]
        wb[1] ~ Rb[1, 1] * b.f[1] + Rb[1, 2] * b.f[2] + Rb[1, 3] * b.f[3]
        wb[2] ~ Rb[2, 1] * b.f[1] + Rb[2, 2] * b.f[2] + Rb[2, 3] * b.f[3]
        wb[3] ~ Rb[3, 1] * b.f[1] + Rb[3, 2] * b.f[2] + Rb[3, 3] * b.f[3]
        vb[1] ~ Rb[1, 1] * b.f[4] + Rb[1, 2] * b.f[5] + Rb[1, 3] * b.f[6]
        vb[2] ~ Rb[2, 1] * b.f[4] + Rb[2, 2] * b.f[5] + Rb[2, 3] * b.f[6]
        vb[3] ~ Rb[3, 1] * b.f[4] + Rb[3, 2] * b.f[5] + Rb[3, 3] * b.f[6]
        # Material point velocities at the contact point and their difference.
        ua[1] ~ va[1] + wa[2] * la[3] - wa[3] * la[2]
        ua[2] ~ va[2] + wa[3] * la[1] - wa[1] * la[3]
        ua[3] ~ va[3] + wa[1] * la[2] - wa[2] * la[1]
        ub[1] ~ vb[1] - r * (wb[2] * n[3] - wb[3] * n[2])
        ub[2] ~ vb[2] - r * (wb[3] * n[1] - wb[1] * n[3])
        ub[3] ~ vb[3] - r * (wb[1] * n[2] - wb[2] * n[1])
        uv[1] ~ ub[1] - ua[1]
        uv[2] ~ ub[2] - ua[2]
        uv[3] ~ ub[3] - ua[3]
        un ~ n[1] * uv[1] + n[2] * uv[2] + n[3] * uv[3]
        s1 ~ t1[1] * uv[1] + t1[2] * uv[2] + t1[3] * uv[3]
        s2 ~ t2[1] * uv[1] + t2[2] * uv[2] + t2[3] * uv[3]
        # Normal force (smooth Hunt-Crossley, gated by the finite face).
        rr ~ sqrt(delta * delta + eps * eps)
        x ~ 0.5 * eps * eps / (rr - delta)
        sig ~ x / rr
        xd ~ -sig * un
        xe ~ x * sqrt(x / xref)
        Fk ~ k * xe
        Fx ~ Fk * (1 + c * xd)
        Fc ~ 0.5 * (Fx + sqrt(Fx * Fx + feps * feps))
        qa ~ 0.25 * (1 + tanh((w1 - u1) / we)) * (1 + tanh((w1 + u1) / we))
        qb ~ 0.25 * (1 + tanh((w2 - u2) / we)) * (1 + tanh((w2 + u2) / we))
        gate ~ qa * qb
        f_n ~ gate * sig * Fc
        Ec ~ 0.4 * k * xe * x * gate
        # Friction on the slip (isotropic regularised Coulomb).
        slip ~ sqrt(s1 * s1 + s2 * s2)
        Sn ~ sqrt(s1 * s1 + s2 * s2 + vs * vs)
        cf ~ mu * f_n / Sn
        ft1 ~ -cf * s1
        ft2 ~ -cf * s2
        F[1] ~ f_n * n[1] + ft1 * t1[1] + ft2 * t2[1]
        F[2] ~ f_n * n[2] + ft1 * t1[2] + ft2 * t2[2]
        F[3] ~ f_n * n[3] + ft1 * t1[3] + ft2 * t2[3]
        # Rolling resistance and spin damping on the relative angular velocity.
        wr[1] ~ wb[1] - wa[1]
        wr[2] ~ wb[2] - wa[2]
        wr[3] ~ wb[3] - wa[3]
        wr1 ~ t1[1] * wr[1] + t1[2] * wr[2] + t1[3] * wr[3]
        wr2 ~ t2[1] * wr[1] + t2[2] * wr[2] + t2[3] * wr[3]
        wrn ~ n[1] * wr[1] + n[2] * wr[2] + n[3] * wr[3]
        Wn ~ sqrt(wr1 * wr1 + wr2 * wr2 + ws * ws)
        cr ~ crr * r * f_n / Wn
        Tr[1] ~ -cr * (wr1 * t1[1] + wr2 * t2[1]) - bsp * wrn * n[1]
        Tr[2] ~ -cr * (wr1 * t1[2] + wr2 * t2[2]) - bsp * wrn * n[2]
        Tr[3] ~ -cr * (wr1 * t1[3] + wr2 * t2[3]) - bsp * wrn * n[3]
        Pd ~ gate * (Fc - Fk) * xd + cf * (s1 * s1 + s2 * s2) + cr * (wr1 * wr1 + wr2 * wr2) + bsp * wrn * wrn
        # Torques: on the sphere about its centre ((-r n) x F + Tr), on body a about its origin
        # (la x (-F) - Tr).
        Tb[1] ~ -r * (n[2] * F[3] - n[3] * F[2]) + Tr[1]
        Tb[2] ~ -r * (n[3] * F[1] - n[1] * F[3]) + Tr[2]
        Tb[3] ~ -r * (n[1] * F[2] - n[2] * F[1]) + Tr[3]
        Ta[1] ~ -(la[2] * F[3] - la[3] * F[2]) - Tr[1]
        Ta[2] ~ -(la[3] * F[1] - la[1] * F[3]) - Tr[2]
        Ta[3] ~ -(la[1] * F[2] - la[2] * F[1]) - Tr[3]
        # Port efforts: minus the wrenches on the bodies in their body frames.
        b.e[1] ~ -(Rb[1, 1] * Tb[1] + Rb[2, 1] * Tb[2] + Rb[3, 1] * Tb[3])
        b.e[2] ~ -(Rb[1, 2] * Tb[1] + Rb[2, 2] * Tb[2] + Rb[3, 2] * Tb[3])
        b.e[3] ~ -(Rb[1, 3] * Tb[1] + Rb[2, 3] * Tb[2] + Rb[3, 3] * Tb[3])
        b.e[4] ~ -(Rb[1, 1] * F[1] + Rb[2, 1] * F[2] + Rb[3, 1] * F[3])
        b.e[5] ~ -(Rb[1, 2] * F[1] + Rb[2, 2] * F[2] + Rb[3, 2] * F[3])
        b.e[6] ~ -(Rb[1, 3] * F[1] + Rb[2, 3] * F[2] + Rb[3, 3] * F[3])
        a.e[1] ~ -(Ra[1, 1] * Ta[1] + Ra[2, 1] * Ta[2] + Ra[3, 1] * Ta[3])
        a.e[2] ~ -(Ra[1, 2] * Ta[1] + Ra[2, 2] * Ta[2] + Ra[3, 2] * Ta[3])
        a.e[3] ~ -(Ra[1, 3] * Ta[1] + Ra[2, 3] * Ta[2] + Ra[3, 3] * Ta[3])
        a.e[4] ~ Ra[1, 1] * F[1] + Ra[2, 1] * F[2] + Ra[3, 1] * F[3]
        a.e[5] ~ Ra[1, 2] * F[1] + Ra[2, 2] * F[2] + Ra[3, 2] * F[3]
        a.e[6] ~ Ra[1, 3] * F[1] + Ra[2, 3] * F[2] + Ra[3, 3] * F[3]
    end
    @causality begin
        a => (:effort_out, :fixed)
        b => (:effort_out, :fixed)
    end
    @orientation begin
        a => :in
        b => :in
    end
end
