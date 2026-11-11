@block Tyre begin
    # Pneumatic tyre on a wheel that spins on a `Rotor3D`: a radial spring at the lowest rim
    # point (like `RollingDisk`), steady-state Magic Formula forces with combined slip
    # (friction ellipse by normalised slip), first-order tyre (contact patch) deflection
    # dynamics that hold a standing vehicle and keep the model non-stiff at any speed, load
    # sensitivity and rolling resistance.
    #
    # Mounting: the wheel carrier (hub, upright) is a `RigidBody3D` with its frame at the wheel
    # centre and the AXLE ALONG THE BODY z AXIS; the wheel's mass and transverse inertia are in
    # that body, its spin inertia in a `Rotor3D` on the same port. The carrier port attaches
    # DIRECTLY to `p` (the port flow is the carrier twist and the port effort minus the wrench
    # on the carrier about the wheel centre, as for `RollingDisk`), and the spin 1-junction
    # (the `Rotor3D` drive, with the brake and the drive shaft) to `spin` (`spin.f` is the
    # wheel's spin relative to the carrier about +z, `spin.e` minus the torque of the tyre on
    # the wheel about the axle).
    # `g` is the carrier pose, `o`, `fr` the contact plane (a `ContactSurface`, or the tangent
    # plane of a `TerrainSurface` under the wheel), `mus` scales the friction (1 = nominal).
    #
    # Geometry (world frame, n the plane normal, a = R(g) e_z the axle):
    #   u = -(n - (n.a) a)/|.|        direction from the centre to the lowest rim point
    #   d = -n . (centre + R0 u - o)  radial penetration, x its smooth positive part
    #   rp = (R0 - x) u               lever to the contact patch on the ground (loaded radius)
    #   l = a x n /|.|, t = n x l     rolling and lateral directions in the plane (positive spin
    #                                 rolls along l)
    # Velocities: carrier point at the patch vc = v + wc x rp, wheel material point
    # vp = vc + w_rel (a x rp); slip velocities V_sx = l . vp, V_sy = t . vp, longitudinal speed
    # V_x = l . vc and the reference speed V_r = sqrt(V_x^2 + vN^2).
    #
    # Normal force: f_n = sig (kz x + cz xdot)+ (smooth clamp, no pull), sig = dx/dd.
    # Steady state, ISO slips kappa = -V_sx/V_r, tan(alpha) = -V_sy/V_r:
    #   D_i = mus mu_i (1 + dmu dfz) Fz,  dfz = (Fz - Fz0)/Fz0
    #   BCD_x = Kx Fz,   BCD_y = Ky Fz0 sin(2 atan(Fz/(Ky2 Fz0)))
    #   s_im = tan(pi/(2 C_i))/B_i (the peak slip of the pure curve without curvature)
    #   combined: S = sqrt((kappa/s_xm)^2 + (tan(alpha)/s_ym)^2),
    #   F_i0 = D_i sin(C_i atan(T_i S - E_i (T_i S - atan(T_i S)))),   T_i = tan(pi/(2 C_i))
    #   F_x^S = F_x0 (kappa/s_xm)/S,   F_y^S = F_y0 (tan(alpha)/s_ym)/S
    # so each pure-slip curve is the Magic Formula and the saturated resultant lies on the
    # ellipse (F_x/D_x)^2 + (F_y/D_y)^2 = 1. G_i = F_i0/(S s_im) is the secant slip stiffness.
    # Transient (Rill, contact patch deflection x_e, y_e with stiffness c_i and damping d_i):
    # the patch slides at V_s + xe' and carries c xe + d xe' = G (-(V_s + xe')/V_r), so
    #   xe' = -(c_x xe V_r + G_x V_sx)/(d_x V_r + G_x),   F_x = c_x xe + d_x xe'   (and y)
    # In steady state F = F^S; the relaxation length is G/c; at standstill G/V_r is large, the
    # patch sticks (xe' = -V_s) and the tyre is a spring-damper that holds the vehicle; when
    # sliding G is small and the deflection relaxes at c/d. Nothing is stiff at low speed.
    # Rolling resistance: M_rr = -frr Fz R0 tanh(w/wrr) about the axle (w the absolute spin).
    #
    # Wrench on the wheel about its centre: F = f_n n + F_x l + F_y t, M = R0 u x f_n n +
    # rp x (F_x l + F_y t) + M_rr a. The carrier port carries all of it; the axial part
    # T_ax = a . M goes to the spin port (spin.e = -T_ax), and the Rotor3D on the junction puts
    # its reaction back on the carrier, so the carrier feels no axial torque from the tyre.
    # Power: port power = d(Ec)/dt + Pd, Ec = kz x^2/2 + c_x xe^2/2 + c_y ye^2/2,
    # Pd = (f_n - kz x sig) xdot + F_x^2 V_r/G_x + d_x xe'^2 + (y) + frr Fz R0 w tanh(w/wrr) >= 0.
    #
    # Not modelled: aligning moment, camber thrust, overturning moment, tyre inflation.
    @ports begin
        p::Power{Spatial}, [frame = "body"]
        spin::Power{Rotation}
    end
    @inputs begin
        g::Vec{7}, [description = "World pose of the wheel carrier, origin at the wheel centre, axle = body z (D-MB6 chart)"]
        o::Vec{3}, [unit = "m", description = "Contact plane origin in the world (ContactSurface.o)"]
        fr::Vec{9}, [unit = "1", description = "Contact plane frame (n, t1, t2) in the world (ContactSurface.fr)"]
        mus::Real, [unit = "1", description = "Friction scale of the surface (1 = the nominal mu)"]
    end
    @outputs begin
        Fz::Real, [unit = "N", description = "Normal (vertical) tyre force (>= 0)"]
        Fx::Real, [unit = "N", description = "Longitudinal tyre force on the wheel, along the rolling direction"]
        Fy::Real, [unit = "N", description = "Lateral tyre force on the wheel, along t = n x l (to the left of the rolling direction)"]
        kappa::Real, [unit = "1", description = "Longitudinal slip -V_sx/V_r (positive = driving)"]
        alpha::Real, [unit = "rad", description = "Slip angle atan(-V_sy/V_r) (ISO sign: positive alpha gives positive Fy)"]
        Vx::Real, [unit = "m/s", description = "Longitudinal speed of the wheel centre over the ground"]
        omega::Real, [unit = "rad/s", description = "Absolute spin rate of the wheel about the axle"]
        delta::Real, [unit = "m", description = "Radial tyre deflection (signed penetration of the unloaded rim)"]
        xc::Real, [unit = "m", description = "Contact patch, world x"]
        yc::Real, [unit = "m", description = "Contact patch, world y"]
        zc::Real, [unit = "m", description = "Contact patch, world z"]
        Fwx::Real, [unit = "N", description = "Total tyre force on the wheel, world x"]
        Fwy::Real, [unit = "N", description = "Total tyre force on the wheel, world y"]
        Fwz::Real, [unit = "N", description = "Total tyre force on the wheel, world z"]
        camber::Real, [unit = "rad", description = "Inclination of the wheel plane from the plane normal, asin(n . a)"]
        Ec::Real, [unit = "J", description = "Energy stored in the radial spring and the patch deflection"]
        Pd::Real, [unit = "W", description = "Dissipated power (radial damping, sliding, patch damping, rolling resistance)"]
    end
    @parameters begin
        R0::Real = 0.3, [unit = "m", min = 0, description = "Unloaded radius"]
        kz::Real = 2.5e5, [unit = "N/m", min = 0, description = "Radial stiffness"]
        cz::Real = 500.0, [unit = "N*s/m", min = 0, description = "Radial damping"]
        Fz0::Real = 3000.0, [unit = "N", min = 1.0e-6, description = "Nominal load"]
        mux::Real = 1.0, [unit = "1", min = 0, description = "Peak longitudinal friction coefficient at the nominal load"]
        muy::Real = 1.0, [unit = "1", min = 0, description = "Peak lateral friction coefficient at the nominal load"]
        dmu::Real = -0.1, [unit = "1", description = "Load sensitivity of the friction: mu (1 + dmu (Fz - Fz0)/Fz0)"]
        Kx::Real = 20.0, [unit = "1", min = 0, description = "Longitudinal slip stiffness per load, BCD_x/Fz"]
        Cx::Real = 1.6, [unit = "1", min = 1.0e-3, description = "Magic Formula shape factor, longitudinal (1 < C < 2)"]
        Ex::Real = 0.0, [unit = "1", description = "Magic Formula curvature factor, longitudinal (E <= 1)"]
        Ky::Real = 20.0, [unit = "1/rad", min = 0, description = "Cornering stiffness factor: BCD_y = Ky Fz0 sin(2 atan(Fz/(Ky2 Fz0)))"]
        Ky2::Real = 2.0, [unit = "1", min = 1.0e-6, description = "Load (in Fz0) of the largest cornering stiffness"]
        Cy::Real = 1.4, [unit = "1", min = 1.0e-3, description = "Magic Formula shape factor, lateral (1 < C < 2)"]
        Ey::Real = 0.0, [unit = "1", description = "Magic Formula curvature factor, lateral (E <= 1)"]
        cx::Real = 3.0e5, [unit = "N/m", min = 1.0e-6, description = "Longitudinal stiffness of the contact patch"]
        cy::Real = 1.5e5, [unit = "N/m", min = 1.0e-6, description = "Lateral stiffness of the contact patch"]
        dx::Real = 1500.0, [unit = "N*s/m", min = 1.0e-6, description = "Longitudinal damping of the contact patch"]
        dy::Real = 1000.0, [unit = "N*s/m", min = 1.0e-6, description = "Lateral damping of the contact patch"]
        frr::Real = 0.012, [unit = "1", min = 0, description = "Rolling resistance coefficient"]
        wrr::Real = 1.0, [unit = "rad/s", min = 1.0e-9, description = "Spin rate over which the rolling resistance changes sign (tanh)"]
        vN::Real = 0.2, [unit = "m/s", min = 1.0e-9, description = "Regularisation of the reference speed V_r = sqrt(V_x^2 + vN^2)"]
        eps::Real = 1.0e-5, [unit = "m", min = 0, description = "Smoothing length of the penetration positive part"]
        feps::Real = 1.0, [unit = "N", min = 0, description = "Smoothing force of the no-pull clamp"]
        seps::Real = 1.0e-3, [unit = "1", min = 1.0e-12, description = "Regularisation of the combined normalised slip"]
        aeps::Real = 1.0e-6, [unit = "1", min = 0, description = "Regularisation of the rim direction when the wheel lies flat"]
    end
    @variables begin
        xe::Real = 0.0, [unit = "m", state = :prefer, description = "Longitudinal deflection of the contact patch"]
        ye::Real = 0.0, [unit = "m", state = :prefer, description = "Lateral deflection of the contact patch"]
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the carrier frame in the world"]
        an::Real = 0.0, [unit = "1", description = "n . a"]
        wl::Real = 1.0, [unit = "1", description = "Length of the in-plane normal component"]
        ux::Real = 0.0, [unit = "1", description = "Rim direction (centre -> contact), world x"]
        uy::Real = 0.0, [unit = "1", description = "Rim direction, world y"]
        uz::Real = -1.0, [unit = "1", description = "Rim direction, world z"]
        lx::Real = 1.0, [unit = "1", description = "Rolling direction, world x"]
        ly::Real = 0.0, [unit = "1", description = "Rolling direction, world y"]
        lz::Real = 0.0, [unit = "1", description = "Rolling direction, world z"]
        tx::Real = 0.0, [unit = "1", description = "Lateral direction n x l, world x"]
        ty::Real = 1.0, [unit = "1", description = "Lateral direction, world y"]
        tz::Real = 0.0, [unit = "1", description = "Lateral direction, world z"]
        wx::Real = 0.0, [unit = "rad/s", description = "Carrier angular velocity, world x"]
        wy::Real = 0.0, [unit = "rad/s", description = "Carrier angular velocity, world y"]
        wz::Real = 0.0, [unit = "rad/s", description = "Carrier angular velocity, world z"]
        vx::Real = 0.0, [unit = "m/s", description = "Carrier origin (wheel centre) velocity, world x"]
        vy::Real = 0.0, [unit = "m/s", description = "Wheel centre velocity, world y"]
        vz::Real = 0.0, [unit = "m/s", description = "Wheel centre velocity, world z"]
        h::Real = 0.0, [unit = "m", description = "Height of the unloaded rim point over the plane"]
        rr::Real = 1.0e-5, [unit = "m", description = "sqrt(delta^2 + eps^2)"]
        x::Real = 0.0, [unit = "m", description = "Smooth positive penetration"]
        sig::Real = 0.5, [unit = "1", description = "dx/d(delta)"]
        r0x::Real = 0.0, [unit = "m", description = "Lever to the unloaded rim point, world x"]
        r0y::Real = 0.0, [unit = "m", description = "Lever to the unloaded rim point, world y"]
        r0z::Real = -0.3, [unit = "m", description = "Lever to the unloaded rim point, world z"]
        rpx::Real = 0.0, [unit = "m", description = "Lever to the contact patch, world x"]
        rpy::Real = 0.0, [unit = "m", description = "Lever to the contact patch, world y"]
        rpz::Real = -0.3, [unit = "m", description = "Lever to the contact patch, world z"]
        vn::Real = 0.0, [unit = "m/s", description = "Normal velocity of the unloaded rim material point"]
        xd::Real = 0.0, [unit = "m/s", description = "Rate of the smooth penetration"]
        Fk::Real = 0.0, [unit = "N", description = "Radial spring force kz x"]
        Fh::Real = 0.0, [unit = "N", description = "Radial spring-damper force kz x + cz xd"]
        Fc::Real = 0.0, [unit = "N", description = "Clamped radial force"]
        wr::Real = 0.0, [unit = "rad/s", description = "Spin relative to the carrier (spin.f)"]
        cvx::Real = 0.0, [unit = "m/s", description = "Carrier point velocity at the patch, world x"]
        cvy::Real = 0.0, [unit = "m/s", description = "Carrier point velocity at the patch, world y"]
        cvz::Real = 0.0, [unit = "m/s", description = "Carrier point velocity at the patch, world z"]
        pvx::Real = 0.0, [unit = "m/s", description = "Material point velocity at the patch, world x"]
        pvy::Real = 0.0, [unit = "m/s", description = "Material point velocity at the patch, world y"]
        pvz::Real = 0.0, [unit = "m/s", description = "Material point velocity at the patch, world z"]
        Vsx::Real = 0.0, [unit = "m/s", description = "Longitudinal slip velocity l . vp"]
        Vsy::Real = 0.0, [unit = "m/s", description = "Lateral slip velocity t . vp"]
        Vr::Real = 0.2, [unit = "m/s", description = "Reference speed sqrt(V_x^2 + vN^2)"]
        sx::Real = 0.0, [unit = "1", description = "Longitudinal slip -V_sx/V_r"]
        sy::Real = 0.0, [unit = "1", description = "Lateral slip -V_sy/V_r (tan alpha)"]
        dfz::Real = 0.0, [unit = "1", description = "Relative load change (Fz - Fz0)/Fz0"]
        mx::Real = 1.0, [unit = "1", description = "Longitudinal friction coefficient at this load and surface"]
        my::Real = 1.0, [unit = "1", description = "Lateral friction coefficient at this load and surface"]
        Tx::Real = 1.0, [unit = "1", description = "tan(pi/(2 Cx))"]
        Ty::Real = 1.0, [unit = "1", description = "tan(pi/(2 Cy))"]
        Bx::Real = 10.0, [unit = "1", description = "Magic Formula stiffness factor B_x"]
        By::Real = 10.0, [unit = "1", description = "Magic Formula stiffness factor B_y"]
        sxm::Real = 0.1, [unit = "1", description = "Normalising (peak) longitudinal slip"]
        sym::Real = 0.1, [unit = "1", description = "Normalising (peak) lateral slip"]
        S::Real = 1.0e-3, [unit = "1", description = "Combined normalised slip"]
        Xx::Real = 0.0, [unit = "1", description = "Magic Formula argument, longitudinal"]
        Xy::Real = 0.0, [unit = "1", description = "Magic Formula argument, lateral"]
        Fx0::Real = 0.0, [unit = "N", description = "Pure-slip longitudinal force at the combined slip"]
        Fy0::Real = 0.0, [unit = "N", description = "Pure-slip lateral force at the combined slip"]
        Gx::Real = 0.0, [unit = "N", description = "Secant longitudinal slip stiffness"]
        Gy::Real = 0.0, [unit = "N", description = "Secant lateral slip stiffness"]
        xed::Real = 0.0, [unit = "m/s", description = "Rate of the longitudinal patch deflection"]
        yed::Real = 0.0, [unit = "m/s", description = "Rate of the lateral patch deflection"]
        Mrr::Real = 0.0, [unit = "N*m", description = "Rolling resistance moment about the axle"]
        Mx::Real = 0.0, [unit = "N*m", description = "Moment on the wheel about its centre, world x"]
        My::Real = 0.0, [unit = "N*m", description = "Moment on the wheel about its centre, world y"]
        Mz::Real = 0.0, [unit = "N*m", description = "Moment on the wheel about its centre, world z"]
        Tax::Real = 0.0, [unit = "N*m", description = "Moment on the wheel about the axle"]
        Pin::Real = 0.0, [unit = "W", description = "Power absorbed through the ports"]
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
        # Geometry: axle a = R e_z, rim direction u, rolling direction l = a x n, lateral t = n x l.
        an ~ fr[1] * R[1, 3] + fr[2] * R[2, 3] + fr[3] * R[3, 3]
        wl ~ sqrt(1 - an * an + aeps * aeps)
        ux ~ -(fr[1] - an * R[1, 3]) / wl
        uy ~ -(fr[2] - an * R[2, 3]) / wl
        uz ~ -(fr[3] - an * R[3, 3]) / wl
        lx ~ (R[2, 3] * fr[3] - R[3, 3] * fr[2]) / wl
        ly ~ (R[3, 3] * fr[1] - R[1, 3] * fr[3]) / wl
        lz ~ (R[1, 3] * fr[2] - R[2, 3] * fr[1]) / wl
        tx ~ fr[2] * lz - fr[3] * ly
        ty ~ fr[3] * lx - fr[1] * lz
        tz ~ fr[1] * ly - fr[2] * lx
        camber ~ asin(an)
        # Radial penetration of the unloaded rim and its smooth positive part.
        r0x ~ R0 * ux
        r0y ~ R0 * uy
        r0z ~ R0 * uz
        h ~ fr[1] * (g[5] + r0x - o[1]) + fr[2] * (g[6] + r0y - o[2]) + fr[3] * (g[7] + r0z - o[3])
        delta ~ -h
        rr ~ sqrt(delta * delta + eps * eps)
        x ~ 0.5 * eps * eps / (rr - delta)
        sig ~ x / rr
        rpx ~ (R0 - x) * ux
        rpy ~ (R0 - x) * uy
        rpz ~ (R0 - x) * uz
        xc ~ g[5] + rpx
        yc ~ g[6] + rpy
        zc ~ g[7] + rpz
        # Carrier twist in the world (the port flow is the body twist), the spin.
        wx ~ R[1, 1] * p.f[1] + R[1, 2] * p.f[2] + R[1, 3] * p.f[3]
        wy ~ R[2, 1] * p.f[1] + R[2, 2] * p.f[2] + R[2, 3] * p.f[3]
        wz ~ R[3, 1] * p.f[1] + R[3, 2] * p.f[2] + R[3, 3] * p.f[3]
        vx ~ R[1, 1] * p.f[4] + R[1, 2] * p.f[5] + R[1, 3] * p.f[6]
        vy ~ R[2, 1] * p.f[4] + R[2, 2] * p.f[5] + R[2, 3] * p.f[6]
        vz ~ R[3, 1] * p.f[4] + R[3, 2] * p.f[5] + R[3, 3] * p.f[6]
        wr ~ spin.f
        omega ~ wx * R[1, 3] + wy * R[2, 3] + wz * R[3, 3] + wr
        # Normal force (envelope theorem: the penetration rate is -n . v of the rim material point;
        # the spin adds nothing to it, a x u lies in the plane).
        vn ~ fr[1] * (vx + wy * r0z - wz * r0y) + fr[2] * (vy + wz * r0x - wx * r0z) + fr[3] * (vz + wx * r0y - wy * r0x)
        xd ~ -sig * vn
        Fk ~ kz * x
        Fh ~ Fk + cz * xd
        Fc ~ 0.5 * (Fh + sqrt(Fh * Fh + feps * feps))
        Fz ~ sig * Fc
        # Slip velocities at the patch.
        cvx ~ vx + wy * rpz - wz * rpy
        cvy ~ vy + wz * rpx - wx * rpz
        cvz ~ vz + wx * rpy - wy * rpx
        pvx ~ cvx + wr * (R[2, 3] * rpz - R[3, 3] * rpy)
        pvy ~ cvy + wr * (R[3, 3] * rpx - R[1, 3] * rpz)
        pvz ~ cvz + wr * (R[1, 3] * rpy - R[2, 3] * rpx)
        Vx ~ lx * cvx + ly * cvy + lz * cvz
        Vsx ~ lx * pvx + ly * pvy + lz * pvz
        Vsy ~ tx * pvx + ty * pvy + tz * pvz
        Vr ~ sqrt(Vx * Vx + vN * vN)
        sx ~ -Vsx / Vr
        sy ~ -Vsy / Vr
        kappa ~ sx
        alpha ~ atan(sy)
        # Steady-state Magic Formula, combined by normalised slip.
        dfz ~ (Fz - Fz0) / Fz0
        mx ~ mus * mux * max(1 + dmu * dfz, 0.1)
        my ~ mus * muy * max(1 + dmu * dfz, 0.1)
        Tx ~ tan(1.5707963267948966 / Cx)
        Ty ~ tan(1.5707963267948966 / Cy)
        Bx ~ Kx / (Cx * mx)
        By ~ Ky * Fz0 * sin(2 * atan(Fz / (Ky2 * Fz0))) / (Cy * my * (Fz + feps))
        sxm ~ Tx / Bx
        sym ~ Ty / By
        S ~ sqrt((sx / sxm) * (sx / sxm) + (sy / sym) * (sy / sym) + seps * seps)
        Xx ~ Tx * S - Ex * (Tx * S - atan(Tx * S))
        Xy ~ Ty * S - Ey * (Ty * S - atan(Ty * S))
        Fx0 ~ mx * Fz * sin(Cx * atan(Xx))
        Fy0 ~ my * Fz * sin(Cy * atan(Xy))
        Gx ~ Fx0 / (S * sxm)
        Gy ~ Fy0 / (S * sym)
        # Contact patch deflection (Rill's first-order tyre forces).
        xed ~ -(cx * xe * Vr + Gx * Vsx) / (dx * Vr + Gx)
        yed ~ -(cy * ye * Vr + Gy * Vsy) / (dy * Vr + Gy)
        ddt(xe) ~ xed
        ddt(ye) ~ yed
        Fx ~ cx * xe + dx * xed
        Fy ~ cy * ye + dy * yed
        Mrr ~ -frr * Fz * R0 * tanh(omega / wrr)
        # Wrench on the wheel about its centre (world).
        Fwx ~ Fz * fr[1] + Fx * lx + Fy * tx
        Fwy ~ Fz * fr[2] + Fx * ly + Fy * ty
        Fwz ~ Fz * fr[3] + Fx * lz + Fy * tz
        Mx ~ Fz * (r0y * fr[3] - r0z * fr[2]) + rpy * (Fx * lz + Fy * tz) - rpz * (Fx * ly + Fy * ty) + Mrr * R[1, 3]
        My ~ Fz * (r0z * fr[1] - r0x * fr[3]) + rpz * (Fx * lx + Fy * tx) - rpx * (Fx * lz + Fy * tz) + Mrr * R[2, 3]
        Mz ~ Fz * (r0x * fr[2] - r0y * fr[1]) + rpx * (Fx * ly + Fy * ty) - rpy * (Fx * lx + Fy * tx) + Mrr * R[3, 3]
        Tax ~ Mx * R[1, 3] + My * R[2, 3] + Mz * R[3, 3]
        # Port efforts: minus the wrench on the carrier (body frame) and minus the axial moment.
        p.e[1] ~ -(R[1, 1] * Mx + R[2, 1] * My + R[3, 1] * Mz)
        p.e[2] ~ -(R[1, 2] * Mx + R[2, 2] * My + R[3, 2] * Mz)
        p.e[3] ~ -(R[1, 3] * Mx + R[2, 3] * My + R[3, 3] * Mz)
        p.e[4] ~ -(R[1, 1] * Fwx + R[2, 1] * Fwy + R[3, 1] * Fwz)
        p.e[5] ~ -(R[1, 2] * Fwx + R[2, 2] * Fwy + R[3, 2] * Fwz)
        p.e[6] ~ -(R[1, 3] * Fwx + R[2, 3] * Fwy + R[3, 3] * Fwz)
        spin.e ~ -Tax
        # Energy book.
        Ec ~ 0.5 * kz * x * x + 0.5 * cx * xe * xe + 0.5 * cy * ye * ye
        Pin ~ p.e[1] * p.f[1] + p.e[2] * p.f[2] + p.e[3] * p.f[3] + p.e[4] * p.f[4] + p.e[5] * p.f[5] + p.e[6] * p.f[6] + spin.e * spin.f
        Pd ~ Pin - (kz * x * xd + cx * xe * xed + cy * ye * yed)
    end
    @causality begin
        p => (:effort_out, :fixed)
        spin => :effort_out
    end
    @orientation begin
        p => :in
        spin => :in
    end
end
