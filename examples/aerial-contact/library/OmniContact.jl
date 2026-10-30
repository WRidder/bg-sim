@block OmniContact begin
    # Contact of one omnidirectional wheel with a `ContactSurface` plane (the wall): the normal force
    # and the point-frame wrench of `stdlib:contact/ContactPoint`, with ANISOTROPIC traction (X5.8).
    # The stdlib point has two fixed isotropic friction tangents; a wheel does not.
    #
    # Mounting is exactly that of `ContactPoint`: use `FixedTransform3DNeutral` with this contact on
    # side `a` and the end-effector on side `b`, the mount pose being the body pose in the point
    # frame. The pose `g` is the world pose of the contact point (its orientation is the
    # end-effector's), so the wheel drive direction follows the end-effector when it tilts.
    #
    # Normal (smooth Hunt-Crossley, as ContactPoint):  d = -n.(pos - o),  x = (d + sqrt(d^2 + eps^2))/2,
    #   Fk = k x (x/xref)^(1/2),  Fx = Fk (1 + c xdot),  Fc = (Fx + sqrt(Fx^2 + feps^2))/2,  f_n = sigma Fc.
    #
    # Traction. The wheel has a drive direction e (the end-effector's body direction (0, dby, dbz)
    # rotated to the world and projected on the wall, unit length) and free rollers along r = n x e.
    # `u` is the surface speed of the wheel at the contact (m/s, along e, relative to the end-effector:
    # the commanded wheel speed times the wheel radius). With v the world velocity of the contact point,
    #
    #   driven slip   sd = e.v + u        (zero for rolling without slip: the end-effector moves at -u along e)
    #   roller slip   sr = r.v
    #   F_d = mu_d f_n tanh(sd/vs)        regularised Coulomb along the driven direction
    #   F_r = mu_r f_n tanh(sr/vr)        small friction of the free rollers
    #
    # and the world force on the body is f_n n - F_d e - F_r r, so both traction forces act against
    # their slip (dissipation F_d sd + F_r sr >= 0 plus the wheel motor's work F_d u, which the
    # motor supplies). No torque about the contact point.
    @ports p::Power{Spatial}
    @inputs begin
        g::Vec{7}, [description = "World pose of the contact point (D-MB6 chart)"]
        o::Vec{3}, [unit = "m", description = "Plane origin in the world (ContactSurface.o)"]
        fr::Vec{9}, [unit = "1", description = "Plane frame (n, t1, t2) in the world (ContactSurface.fr)"]
        u::Real, [unit = "m/s", description = "Wheel surface speed along the drive direction"]
    end
    @outputs begin
        f_n::Real, [unit = "N", description = "Normal contact force on the body (>= 0)"]
        delta::Real, [unit = "m", description = "Signed penetration (positive = inside the plane)"]
        sd::Real, [unit = "m/s", description = "Slip along the driven direction"]
        sr::Real, [unit = "m/s", description = "Slip along the free rollers"]
        fd::Real, [unit = "N", description = "Traction along the driven direction (acts against sd)"]
        frl::Real, [unit = "N", description = "Roller friction (acts against sr)"]
    end
    @parameters begin
        k::Real = 4.0e3, [unit = "N/m", min = 0, description = "Contact stiffness: force = k x (x/xref)^(1/2) with x in m"]
        xref::Real = 1.0e-3, [unit = "m", min = 1.0e-12, description = "Reference penetration of the 3/2 power"]
        c::Real = 1.0, [unit = "s/m", min = 0, description = "Hunt-Crossley damping coefficient"]
        mu_d::Real = 0.7, [unit = "1", min = 0, description = "Friction coefficient along the driven direction"]
        mu_r::Real = 0.04, [unit = "1", min = 0, description = "Friction coefficient of the free rollers"]
        vs::Real = 2.0e-3, [unit = "m/s", min = 0, description = "Regularisation velocity of the driven direction"]
        vr::Real = 5.0e-3, [unit = "m/s", min = 0, description = "Regularisation velocity of the rollers"]
        dby::Real = 0.0, [unit = "1", description = "Drive direction in the end-effector frame, y component"]
        dbz::Real = 1.0, [unit = "1", description = "Drive direction in the end-effector frame, z component"]
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
        dwx::Real = 0.0, [description = "Drive direction in the world, x"]
        dwy::Real = 0.0, [description = "Drive direction in the world, y"]
        dwz::Real = 1.0, [description = "Drive direction in the world, z"]
        dn::Real = 0.0, [description = "Normal component of the drive direction"]
        tn::Real = 1.0, [description = "Length of the tangential drive direction"]
        ex::Real = 0.0, [description = "Unit drive direction on the wall, x"]
        ey::Real = 0.0, [description = "Unit drive direction on the wall, y"]
        ez::Real = 1.0, [description = "Unit drive direction on the wall, z"]
        rx::Real = 0.0, [description = "Roller direction n x e, x"]
        ry::Real = 1.0, [description = "Roller direction, y"]
        rz::Real = 0.0, [description = "Roller direction, z"]
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
        dwx ~ R[1, 2] * dby + R[1, 3] * dbz
        dwy ~ R[2, 2] * dby + R[2, 3] * dbz
        dwz ~ R[3, 2] * dby + R[3, 3] * dbz
        dn ~ fr[1] * dwx + fr[2] * dwy + fr[3] * dwz
        tn ~ sqrt((dwx - dn * fr[1]) * (dwx - dn * fr[1]) + (dwy - dn * fr[2]) * (dwy - dn * fr[2]) + (dwz - dn * fr[3]) * (dwz - dn * fr[3]) + 1.0e-12)
        ex ~ (dwx - dn * fr[1]) / tn
        ey ~ (dwy - dn * fr[2]) / tn
        ez ~ (dwz - dn * fr[3]) / tn
        rx ~ fr[2] * ez - fr[3] * ey
        ry ~ fr[3] * ex - fr[1] * ez
        rz ~ fr[1] * ey - fr[2] * ex
        sd ~ ex * v1 + ey * v2 + ez * v3 + u
        sr ~ rx * v1 + ry * v2 + rz * v3
        fd ~ mu_d * f_n * tanh(sd / vs)
        frl ~ mu_r * f_n * tanh(sr / vr)
        Fw1 ~ f_n * fr[1] - fd * ex - frl * rx
        Fw2 ~ f_n * fr[2] - fd * ey - frl * ry
        Fw3 ~ f_n * fr[3] - fd * ez - frl * rz
        p.e[1] ~ 0
        p.e[2] ~ 0
        p.e[3] ~ 0
        p.e[4] ~ R[1, 1] * Fw1 + R[2, 1] * Fw2 + R[3, 1] * Fw3
        p.e[5] ~ R[1, 2] * Fw1 + R[2, 2] * Fw2 + R[3, 2] * Fw3
        p.e[6] ~ R[1, 3] * Fw1 + R[2, 3] * Fw2 + R[3, 3] * Fw3
    end
    @causality p => (:effort_out, :fixed)
end
