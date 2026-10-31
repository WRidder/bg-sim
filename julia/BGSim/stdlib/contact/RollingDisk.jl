@block RollingDisk begin
    # Compliant contact of a rolling wheel (a disc of radius `radius`, optionally with a
    # toroidal crown of radius `crown`) with a `ContactSurface` plane. Unlike `ContactPoint`,
    # whose point is fixed in the body, the contact point of a wheel travels around the rim:
    # it is recomputed at every instant as the lowest point of the rim towards the plane.
    #
    # Mounting: bond the wheel body's port (`RigidBody3D.p`, a 1-junction) DIRECTLY to `p`
    # (bond from the body to this element), with the body frame at the wheel centre and the
    # AXLE ALONG THE BODY z AXIS. As for `ContactPoint` on its mount, the port flow is then the
    # NEGATIVE body twist `-[w; v]` (body frame) and the port effort is the contact wrench ON
    # the body about its centre, so the port power `e . f` is the power absorbed by the
    # contact (spring storage + dissipation). `g` is the world pose of the wheel centre (the
    # body pose, e.g. a `PoseIntegrator3D` output).
    #
    # Geometry (world frame, `n` the plane normal, `a = R(g) e_z` the axle):
    #   u      = -(n - (n.a) a) / sqrt(1 - (n.a)^2 + aeps^2)   direction from the centre to the
    #                                                          lowest rim point (in the wheel plane)
    #   r      = radius u - crown n                             lever from the centre to the contact
    #   d      = -n . (centre + r - o)                          signed penetration (positive = inside)
    #   v_p    = v_centre + w x r                               velocity of the rim material point
    # The lowest point minimises the height over the rim, so the rate of the penetration is
    # `-n . v_p` (the envelope theorem): the spring force does exactly the work `dEc/dt`.
    #
    # Normal force: the smooth Hunt-Crossley law of `ContactPoint` (Hertz exponent 3/2, smooth
    # positive part and no-pull clamp, no events):
    #   x = (d + sqrt(d^2 + eps^2))/2,  Fk = k x (x/xref)^(1/2),  Fc = clamp(Fk (1 + c xdot)),
    #   f_n = sigma Fc  along +n.
    # Tangential force: ISOTROPIC regularised Coulomb friction on the slip `s = v_p - (n.v_p) n`
    # (the in-plane velocity of the material point; zero when the wheel rolls without slipping):
    #   F_t = -(mu f_n / sqrt(|s|^2 + vs^2) + bt) s,
    # whose magnitude tends to `mu f_n` when `|s| >> vs`. A wheel that rolls under a side or a
    # drive force `F` creeps at `|s| = vs F / sqrt((mu f_n)^2 - F^2)` (about `vs F/(mu f_n)`):
    # with `vs = 1 mm/s` that is far below a millimetre per second for any force well inside
    # the friction cone. Optional spin (drilling) damping `-bsp (n.w) n` about the normal.
    #
    # Wrench on the body about its centre: `F = f_n n + F_t` at the contact point and the spin
    # torque, rotated into the body frame. Port effort = that wrench; port power
    # = -(F . v_p + tau_sp . w) = dEc/dt + Pd, with the dissipation
    #   Pd = (Fc - Fk) xdot + mu f_n |s|^2 / sqrt(|s|^2 + vs^2) + bt |s|^2 + bsp (n.w)^2 >= 0.
    #
    # The axle must not be (nearly) normal to the plane (a wheel lying flat): `aeps` only keeps
    # the direction `u` finite there.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs begin
        g::Vec{7}, [description = "World pose of the wheel centre, axle = body z (D-MB6 chart)"]
        o::Vec{3}, [unit = "m", description = "Plane origin in the world (ContactSurface.o)"]
        fr::Vec{9}, [unit = "1", description = "Plane frame (n, t1, t2) in the world (ContactSurface.fr)"]
    end
    @outputs begin
        f_n::Real, [unit = "N", description = "Normal contact force on the wheel (>= 0)"]
        delta::Real, [unit = "m", description = "Signed penetration of the rim (positive = inside the plane)"]
        s_lon::Real, [unit = "m/s", description = "Slip velocity along the rolling direction (a x n)"]
        s_lat::Real, [unit = "m/s", description = "Slip velocity across the wheel (n x (a x n))"]
        f_lon::Real, [unit = "N", description = "Tangential force on the wheel along the rolling direction"]
        f_lat::Real, [unit = "N", description = "Tangential force on the wheel across the wheel"]
        xc::Real, [unit = "m", description = "Contact point, world x"]
        yc::Real, [unit = "m", description = "Contact point, world y"]
        zc::Real, [unit = "m", description = "Contact point, world z"]
        camber::Real, [unit = "rad", description = "Lean of the wheel plane from the plane normal, asin(n . a)"]
        Ec::Real, [unit = "J", description = "Energy stored in the normal spring"]
        Pd::Real, [unit = "W", description = "Dissipated power (normal damping, friction, spin damping)"]
    end
    @parameters begin
        radius::Real = 0.2, [unit = "m", min = 0, description = "Wheel radius (to the crown centre line)"]
        crown::Real = 0.0, [unit = "m", min = 0, description = "Crown (tyre section) radius of a toroidal wheel; 0 = knife edge"]
        k::Real = 1.0e5, [unit = "N/m", min = 0, description = "Contact stiffness: force = k x (x/xref)^(1/2) with x in m (Hertz, exponent 3/2)"]
        xref::Real = 1.0e-3, [unit = "m", min = 1.0e-12, description = "Reference penetration of the 3/2 power (force = k xref at x = xref)"]
        c::Real = 1.0, [unit = "s/m", min = 0, description = "Hunt-Crossley damping coefficient: force = Fk (1 + c xdot)"]
        mu::Real = 0.8, [unit = "1", min = 0, description = "Coulomb friction coefficient (isotropic)"]
        vs::Real = 1.0e-3, [unit = "m/s", min = 1.0e-12, description = "Friction regularisation velocity"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Optional viscous tangential damping"]
        bsp::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Optional spin (drilling) damping about the plane normal"]
        eps::Real = 1.0e-6, [unit = "m", min = 0, description = "Smoothing length of the penetration positive part"]
        feps::Real = 1.0e-6, [unit = "N", min = 0, description = "Smoothing force of the no-pull clamp"]
        aeps::Real = 1.0e-6, [unit = "1", min = 0, description = "Regularisation of the rim direction when the wheel lies flat"]
    end
    @variables begin
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the wheel frame in the world"]
        an::Real = 0.0, [unit = "1", description = "n . a (sine of the camber)"]
        wl::Real = 1.0, [unit = "1", description = "Length of the in-plane normal component"]
        ux::Real = 0.0, [unit = "1", description = "Rim direction (centre -> contact), world x"]
        uy::Real = 0.0, [unit = "1", description = "Rim direction, world y"]
        uz::Real = -1.0, [unit = "1", description = "Rim direction, world z"]
        rx::Real = 0.0, [unit = "m", description = "Lever centre -> contact, world x"]
        ry::Real = 0.0, [unit = "m", description = "Lever centre -> contact, world y"]
        rz::Real = -0.2, [unit = "m", description = "Lever centre -> contact, world z"]
        wx::Real = 0.0, [unit = "rad/s", description = "Wheel angular velocity, world x"]
        wy::Real = 0.0, [unit = "rad/s", description = "Wheel angular velocity, world y"]
        wz::Real = 0.0, [unit = "rad/s", description = "Wheel angular velocity, world z"]
        v1::Real = 0.0, [unit = "m/s", description = "Rim point velocity, world x"]
        v2::Real = 0.0, [unit = "m/s", description = "Rim point velocity, world y"]
        v3::Real = 0.0, [unit = "m/s", description = "Rim point velocity, world z"]
        vn::Real = 0.0, [unit = "m/s", description = "Normal component n . v_p"]
        sx::Real = 0.0, [unit = "m/s", description = "Slip, world x"]
        sy::Real = 0.0, [unit = "m/s", description = "Slip, world y"]
        sz::Real = 0.0, [unit = "m/s", description = "Slip, world z"]
        sn::Real = 1.0e-3, [unit = "m/s", description = "sqrt(|s|^2 + vs^2)"]
        h::Real = 0.0, [unit = "m", description = "Signed distance n . (contact - o)"]
        rr::Real = 1.0e-6, [unit = "m", description = "sqrt(delta^2 + eps^2)"]
        x::Real = 1.0e-3, [unit = "m", description = "Smooth positive penetration"]
        sig::Real = 0.5, [unit = "1", description = "dx/d(delta)"]
        xd::Real = 0.0, [unit = "m/s", description = "Rate of the smooth penetration"]
        xe::Real = 1.0e-4, [unit = "m", description = "x (x/xref)^(1/2)"]
        Fk::Real = 1.0, [unit = "N", description = "Spring force k x (x/xref)^(1/2)"]
        Fx::Real = 1.0, [unit = "N", description = "Hunt-Crossley force Fk (1 + c xd)"]
        Fc::Real = 1.0, [unit = "N", description = "Clamped Hunt-Crossley force"]
        cf::Real = 0.0, [unit = "N*s/m", description = "Friction coefficient of the slip, mu f_n / sn + bt"]
        wn::Real = 0.0, [unit = "rad/s", description = "Spin rate about the normal, n . w"]
        Fw1::Real = 0.0, [unit = "N", description = "World force on the wheel, x"]
        Fw2::Real = 0.0, [unit = "N", description = "World force on the wheel, y"]
        Fw3::Real = 0.0, [unit = "N", description = "World force on the wheel, z"]
        Tw1::Real = 0.0, [unit = "N*m", description = "World torque on the wheel about its centre, x"]
        Tw2::Real = 0.0, [unit = "N*m", description = "World torque on the wheel about its centre, y"]
        Tw3::Real = 0.0, [unit = "N*m", description = "World torque on the wheel about its centre, z"]
        lx::Real = 1.0, [unit = "1", description = "Rolling direction a x n / wl, world x"]
        ly::Real = 0.0, [unit = "1", description = "Rolling direction, world y"]
        lz::Real = 0.0, [unit = "1", description = "Rolling direction, world z"]
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
        # Axle a = R e_z (third column); the rim direction towards the plane.
        an ~ fr[1] * R[1, 3] + fr[2] * R[2, 3] + fr[3] * R[3, 3]
        wl ~ sqrt(1 - an * an + aeps * aeps)
        ux ~ -(fr[1] - an * R[1, 3]) / wl
        uy ~ -(fr[2] - an * R[2, 3]) / wl
        uz ~ -(fr[3] - an * R[3, 3]) / wl
        rx ~ radius * ux - crown * fr[1]
        ry ~ radius * uy - crown * fr[2]
        rz ~ radius * uz - crown * fr[3]
        # Rolling direction l = a x n / wl and the camber.
        lx ~ (R[2, 3] * fr[3] - R[3, 3] * fr[2]) / wl
        ly ~ (R[3, 3] * fr[1] - R[1, 3] * fr[3]) / wl
        lz ~ (R[1, 3] * fr[2] - R[2, 3] * fr[1]) / wl
        camber ~ asin(an)
        # World angular velocity and the rim point velocity v_p = R v + w x r (the port flow is
        # the NEGATIVE body twist).
        wx ~ -(R[1, 1] * p.f[1] + R[1, 2] * p.f[2] + R[1, 3] * p.f[3])
        wy ~ -(R[2, 1] * p.f[1] + R[2, 2] * p.f[2] + R[2, 3] * p.f[3])
        wz ~ -(R[3, 1] * p.f[1] + R[3, 2] * p.f[2] + R[3, 3] * p.f[3])
        v1 ~ -(R[1, 1] * p.f[4] + R[1, 2] * p.f[5] + R[1, 3] * p.f[6]) + (wy * rz - wz * ry)
        v2 ~ -(R[2, 1] * p.f[4] + R[2, 2] * p.f[5] + R[2, 3] * p.f[6]) + (wz * rx - wx * rz)
        v3 ~ -(R[3, 1] * p.f[4] + R[3, 2] * p.f[5] + R[3, 3] * p.f[6]) + (wx * ry - wy * rx)
        vn ~ fr[1] * v1 + fr[2] * v2 + fr[3] * v3
        # Contact point and penetration.
        xc ~ g[5] + rx
        yc ~ g[6] + ry
        zc ~ g[7] + rz
        h ~ fr[1] * (xc - o[1]) + fr[2] * (yc - o[2]) + fr[3] * (zc - o[3])
        delta ~ -h
        rr ~ sqrt(delta * delta + eps * eps)
        x ~ 0.5 * eps * eps / (rr - delta)
        sig ~ x / rr
        xd ~ -sig * vn
        xe ~ x * sqrt(x / xref)
        Fk ~ k * xe
        Fx ~ Fk * (1 + c * xd)
        Fc ~ 0.5 * (Fx + sqrt(Fx * Fx + feps * feps))
        f_n ~ sig * Fc
        Ec ~ 0.4 * k * xe * x
        # Isotropic regularised Coulomb friction on the in-plane slip.
        sx ~ v1 - vn * fr[1]
        sy ~ v2 - vn * fr[2]
        sz ~ v3 - vn * fr[3]
        sn ~ sqrt(sx * sx + sy * sy + sz * sz + vs * vs)
        cf ~ mu * f_n / sn + bt
        s_lon ~ lx * sx + ly * sy + lz * sz
        s_lat ~ (fr[2] * lz - fr[3] * ly) * sx + (fr[3] * lx - fr[1] * lz) * sy + (fr[1] * ly - fr[2] * lx) * sz
        f_lon ~ -cf * s_lon
        f_lat ~ -cf * s_lat
        wn ~ fr[1] * wx + fr[2] * wy + fr[3] * wz
        Pd ~ (Fc - Fk) * xd + cf * (sx * sx + sy * sy + sz * sz) + bsp * wn * wn
        Fw1 ~ f_n * fr[1] - cf * sx
        Fw2 ~ f_n * fr[2] - cf * sy
        Fw3 ~ f_n * fr[3] - cf * sz
        Tw1 ~ ry * Fw3 - rz * Fw2 - bsp * wn * fr[1]
        Tw2 ~ rz * Fw1 - rx * Fw3 - bsp * wn * fr[2]
        Tw3 ~ rx * Fw2 - ry * Fw1 - bsp * wn * fr[3]
        # Port effort = body-frame wrench on the wheel (with the negative twist as the flow, the
        # port power is the absorbed power).
        p.e[1] ~ R[1, 1] * Tw1 + R[2, 1] * Tw2 + R[3, 1] * Tw3
        p.e[2] ~ R[1, 2] * Tw1 + R[2, 2] * Tw2 + R[3, 2] * Tw3
        p.e[3] ~ R[1, 3] * Tw1 + R[2, 3] * Tw2 + R[3, 3] * Tw3
        p.e[4] ~ R[1, 1] * Fw1 + R[2, 1] * Fw2 + R[3, 1] * Fw3
        p.e[5] ~ R[1, 2] * Fw1 + R[2, 2] * Fw2 + R[3, 2] * Fw3
        p.e[6] ~ R[1, 3] * Fw1 + R[2, 3] * Fw2 + R[3, 3] * Fw3
    end
    @causality p => (:effort_out, :fixed)
end
