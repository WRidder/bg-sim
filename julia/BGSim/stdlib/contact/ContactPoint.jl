@block ContactPoint begin
    # Compliant point contact against a `ContactSurface` plane (F11, J-MB13). The element is a
    # one-port resistive/storage element on a spatial bond: the port frame IS the contact
    # point frame, and the port effort is computed from the port flow, so the element is
    # power-consistent with the bond.
    #
    # Mounting (causality): use `FixedTransform3DNeutral` with the CONTACT on side `a` (parent)
    # and the body on side `b` (child); the mount pose is the body pose in the point frame (for
    # a translation-only point at body offset r that is -r). The body's flow then determines
    # `p.f` explicitly and `p.e` flows back as `b.e = Ad^T a.e` with no algebraic loop (the
    # other orientation needs the inverse of `Ad(g)` and leaves a nonlinear initialisation).
    # Because `a.f = -Ad(g) b.f`, the port flow is the NEGATIVE point twist, and the port
    # effort is `+(wrench on the body)` expressed in the point frame, so the port power
    # `e . f = -F . v` is the power absorbed by the contact (storage + dissipation).
    #
    # Inputs: `g` the point's world pose on the D-MB6 chart (compose the body pose with the
    # point's `LocalPose3D` by `ComposePose3D`; the position gives the penetration and the
    # rotation maps the flow to the world frame), and the plane signals `o`, `fr` of
    # the port-frame origin, in the point frame), rotated to the world by `R(g)`.
    #
    # Normal force (smooth Hunt-Crossley, no events and no `max`):
    #   d      = -n . (pos - o)                   signed penetration (positive = inside)
    #   x      = (d + sqrt(d^2 + eps^2)) / 2      (= eps^2/(2 (r - d)), cancellation-free) smooth positive part, sigma = dx/dd
    #   xdot   = sigma * d/dt(d) = -sigma n . v   (d/dt(d) = -n . v from the port flow)
    #   Fx     = k x (x/xref)^(1/2) (1 + c xdot)   Hunt-Crossley force, Hertz exponent 3/2
    #   Fc     = (Fx + sqrt(Fx^2 + feps^2)) / 2   smooth "no pull" clamp
    #   f_n    = sigma Fc                         force on the body along the normal
    # Stored energy `Ec = (2/5) k x^2 (x/xref)^(1/2)`; the normal dissipation is `(Fc - Fk) xdot`
    # (power `f_n d/dt(d) = Fc xdot = dEc/dt + (Fc - Fk) xdot`, `Fk = k x (x/xref)^(1/2)`).
    #
    # Tangential forces: two scalar regularised Coulomb dampers along the plane tangents `t1`,
    # `t2` (the `1<2>` tangent of the design as two scalar 1-junctions):
    #   F_ti = mu f_n tanh(s_i / vs) + bt s_i,     s_i = t_i . v_world
    # acting against the slip, so each dissipates `F_ti s_i >= 0`. An exactly stuck contact
    # (`s = 0`) is replaced by a creep `s ~ vs atanh(F_t / (mu f_n))` (the regularisation,
    # documented in the tests).
    #
    # The world force `F_w = f_n n - F_t1 t1 - F_t2 t2` acts at the point with no torque about
    # the point; in the point frame the wrench on the body is `[0; R^T F_w]` and the port effort
    # equals it (see the mounting note above for the sign convention). The
    # torque and force components are written separately (N*m vs N).
    @ports p::Power{Spatial}
    @inputs begin
        g::Vec{7}, [description = "World pose of the contact point (D-MB6 chart)"]
        o::Vec{3}, [unit = "m", description = "Plane origin in the world (ContactSurface.o)"]
        fr::Vec{9}, [unit = "1", description = "Plane frame (n, t1, t2) in the world (ContactSurface.fr)"]
    end
    @outputs begin
        f_n::Real, [unit = "N", description = "Normal contact force on the body (>= 0)"]
        delta::Real, [unit = "m", description = "Signed penetration (positive = inside the plane)"]
        s1::Real, [unit = "m/s", description = "Slip velocity along tangent 1"]
        s2::Real, [unit = "m/s", description = "Slip velocity along tangent 2"]
        ft1::Real, [unit = "N", description = "Friction force magnitude along tangent 1 (acts against s1)"]
        ft2::Real, [unit = "N", description = "Friction force magnitude along tangent 2 (acts against s2)"]
        Ec::Real, [unit = "J", description = "Energy stored in the normal spring"]
        Pd::Real, [unit = "W", description = "Dissipated power (normal damping + friction)"]
    end
    @parameters begin
        k::Real = 1.0e4, [unit = "N/m", min = 0, description = "Contact stiffness: force = k x (x/xref)^(1/2) with x in m (Hertz, exponent 3/2)"]
        xref::Real = 1.0e-3, [unit = "m", min = 1.0e-12, description = "Reference penetration that makes the 3/2 power unit-clean (force = k xref at x = xref)"]
        c::Real = 1.0, [unit = "s/m", min = 0, description = "Hunt-Crossley damping coefficient: force = Fk (1 + c xdot)"]
        mu::Real = 0.5, [unit = "1", min = 0, description = "Coulomb friction coefficient"]
        vs::Real = 1.0e-3, [unit = "m/s", min = 0, description = "Friction regularisation velocity (tanh(s/vs))"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Optional viscous tangential damping"]
        eps::Real = 1.0e-6, [unit = "m", min = 0, description = "Smoothing length of the penetration positive part"]
        feps::Real = 1.0e-6, [unit = "N", min = 0, description = "Smoothing force of the no-pull clamp"]
    end
    @variables begin
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the point frame in the world"]
        v1::Real = 0.0, [unit = "m/s", description = "Point velocity, world x"]
        v2::Real = 0.0, [unit = "m/s", description = "Point velocity, world y"]
        v3::Real = 0.0, [unit = "m/s", description = "Point velocity, world z"]
        h::Real = 0.0, [unit = "m", description = "Signed distance n . (pos - o)"]
        r::Real = 1.0e-6, [unit = "m", description = "sqrt(delta^2 + eps^2)"]
        x::Real = 1.0e-3, [unit = "m", description = "Smooth positive penetration"]
        sig::Real = 0.5, [unit = "1", description = "dx/d(delta)"]
        xd::Real = 0.0, [unit = "m/s", description = "Rate of the smooth penetration"]
        xe::Real = 1.0e-4, [unit = "m", description = "x (x/xref)^(1/2)"]
        Fk::Real = 1.0, [unit = "N", description = "Spring force k x (x/xref)^(1/2)"]
        Fx::Real = 1.0, [unit = "N", description = "Hunt-Crossley force Fk (1 + c xd)"]
        Fc::Real = 1.0, [unit = "N", description = "Clamped Hunt-Crossley force"]
        Fw1::Real = 0.0, [unit = "N", description = "World force on the body, x"]
        Fw2::Real = 0.0, [unit = "N", description = "World force on the body, y"]
        Fw3::Real = 0.0, [unit = "N", description = "World force on the body, z"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        # Point velocity in the world: the port flow is the NEGATIVE point twist (the mount's a-side).
        v1 ~ -(R[1, 1] * p.f[4] + R[1, 2] * p.f[5] + R[1, 3] * p.f[6])
        v2 ~ -(R[2, 1] * p.f[4] + R[2, 2] * p.f[5] + R[2, 3] * p.f[6])
        v3 ~ -(R[3, 1] * p.f[4] + R[3, 2] * p.f[5] + R[3, 3] * p.f[6])
        h ~ fr[1] * (g[5] - o[1]) + fr[2] * (g[6] - o[2]) + fr[3] * (g[7] - o[3])
        delta ~ -h
        r ~ sqrt(delta * delta + eps * eps)
        x ~ 0.5 * eps * eps / (r - delta)
        sig ~ x / r
        xd ~ -sig * (fr[1] * v1 + fr[2] * v2 + fr[3] * v3)
        xe ~ x * sqrt(x / xref)
        Fk ~ k * xe
        Fx ~ Fk * (1 + c * xd)
        Fc ~ 0.5 * (Fx + sqrt(Fx * Fx + feps * feps))
        f_n ~ sig * Fc
        Ec ~ 0.4 * k * xe * x
        s1 ~ fr[4] * v1 + fr[5] * v2 + fr[6] * v3
        s2 ~ fr[7] * v1 + fr[8] * v2 + fr[9] * v3
        ft1 ~ mu * f_n * tanh(s1 / vs) + bt * s1
        ft2 ~ mu * f_n * tanh(s2 / vs) + bt * s2
        Pd ~ (Fc - Fk) * xd + ft1 * s1 + ft2 * s2
        Fw1 ~ f_n * fr[1] - ft1 * fr[4] - ft2 * fr[7]
        Fw2 ~ f_n * fr[2] - ft1 * fr[5] - ft2 * fr[8]
        Fw3 ~ f_n * fr[3] - ft1 * fr[6] - ft2 * fr[9]
        # Port effort = +(point-frame wrench [0; R^T F_w]) on the body: with `p.f` = -(point twist)
        # the port power `e . f = -F . v` is the power ABSORBED by the contact.
        p.e[1] ~ 0
        p.e[2] ~ 0
        p.e[3] ~ 0
        p.e[4] ~ R[1, 1] * Fw1 + R[2, 1] * Fw2 + R[3, 1] * Fw3
        p.e[5] ~ R[1, 2] * Fw1 + R[2, 2] * Fw2 + R[3, 2] * Fw3
        p.e[6] ~ R[1, 3] * Fw1 + R[2, 3] * Fw2 + R[3, 3] * Fw3
    end
    @causality p => (:effort_out, :fixed)
end
