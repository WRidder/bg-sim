@block SuctionCup begin
    # Bellows suction cup between a gripper and a part, with its vacuum chamber (a two-port
    # spatial element plus a Hydraulic port for the vacuum line).
    #
    # Mounting (as `ContactPoint`): side `a` is the cup mount frame on the gripper, side `b`
    # the attach point on the part surface, each through a `FixedTransform3DNeutral` with the
    # CUP on side `a` of the mount (mount pose = the gripper frame, resp. the part body frame,
    # seen from the point). Both port flows are then the NEGATIVE frame twists, `Vp = -a.f`
    # (cup frame, gripper side) and `Vc = -b.f` (part point frame), and the port efforts are
    # the wrenches ON the gripper (`a.e`, about the cup origin, cup frame) and ON the part
    # (`b.e`, about the attach point, point frame). The cup axis is the -z axis of the cup
    # frame: the part hangs below the cup.
    #
    # Kinematics (no pose inputs): the relative pose of the part point in the cup frame is
    # integrated from the relative twist, like `Spherical3D`:
    #   r' = R vc - (vp + wp x r),   Q' = 1/2 Q (x) [0, wr],   wr = wc - R^T wp,
    # with `R = R(Q)` the rotation of the point frame in the cup frame (start: r = (0,0,-L0),
    # Q = identity, so the part must start with its point frame aligned with the cup).
    #
    # Bellows and seal (the vacuum force is a holding CAPACITY, not a pressure x area force):
    #   s = -r_z separation, ext = s - L0                           bellows extension
    #   Fs = k_ax ext + d_ax s' + A_fold dp - F_bot                 bellows tension (pull > 0)
    #   Fcap = A_eff dp,  dp = pos(-p)                              holding force of the seal
    #   T = smin(Fs, Fcap)                                          transmitted axial force
    #   N = Fcap - T                                                lip contact force (>= 0)
    #   Mb = 2 qw (k_tilt kf qx, k_tilt kf qy, k_tor qz) + d_rot wr bellows bending/torsion
    #   h = pos((Fs + 4|Mb_xy|/D_lip - Fcap) / k_ax)                lip lift (gap), m
    # Nonlinear bellows (all OFF by default: k_bot = A_fold = c_vac = c_ext = 0 give the linear
    # cup exactly):
    #   * bottoming: beyond the compression stroke s_bot the folds stack up and the cup stiffens
    #     progressively, F_bot = k_bot xb (xb / x_bot)^(n_bot - 1), xb = pos(-ext - s_bot) (a
    #     push; smooth: pos uses h_eps, so the force-stroke curve has no kink, and its slope is
    #     n_bot k_bot at xb = x_bot);
    #   * vacuum lift stroke: the vacuum acting on the folded annulus A_fold pulls the bellows
    #     shut, A_fold dp; an unloaded cup contracts by ext = -A_fold dp / k_ax (until it
    #     bottoms), a loaded one by T = k_ax ext + A_fold dp. The holding capacity is unchanged;
    #   * lateral and tilt stiffness: k_lat kf and k_tilt kf with
    #     kf = (1 + c_vac dp / p_atm) exp(-c_ext ext / L0)
    #     (a cup under vacuum and compressed stiffens, an extended one softens).
    # Hysteresis: the Kelvin dampers d_ax, d_lat, d_rot carry the rate-dependent losses of the
    # rubber; the rate-independent (Dahl-type) loop of a bellows is small next to them at
    # handling speeds and is not modelled (the lateral Dahl law below is the lip slip).
    # so the cup pushes without limit (lip support), pulls up to the vacuum force, and a lip
    # that lifts (pull-off, or one side under a tilting moment: a ring of diameter D_lip under
    # an axial force F and a moment M lifts when F + 4M/D_lip > Fcap) opens a leak.
    # Lateral: the bellows deflection `e` is the elastic part of the relative lateral motion;
    # the lip slips over the surface with a generalised Dahl law of exponent 5,
    #   e' = v - |v| rho |rho|^4 / (1 + |rho|^4/100),   rho = k_lat kf e / (mu N + F_min),
    # elastic below the friction capacity mu N, sliding at it (F_lat = k_lat kf e + d_lat e').
    #
    # Vacuum chamber (free-air volume flows, as generator datasheets give them; isothermal):
    #   p' = p_atm (Q_leak + Q_por + vac.f) / V,      vac.e = p (gauge pressure, < 0 = vacuum)
    #   Q_por  = perm A_eff dp                        Darcy flow through a porous part
    #   Q_leak = Cd A_lip dP sqrt(2 / (rho sqrt(dP^2 + p_tr^2))), dP = -p,
    #   A_lip  = A_lip0 + pi D_lip h                  lip roughness leak plus the lift gap.
    # `pos(x) = (x + sqrt(x^2 + eps^2))/2`, `smin(a, b) = (a + b - sqrt((a - b)^2 + F_eps^2))/2`.
    #
    # Utilisation `U = (T + 4|M_xy|/D_lip + |F_lat|/mu) / (Fcap + F_eps)`: 1 is the edge of
    # pull-off/peel (T + 4M/D = Fcap) and of shear slip (|F_lat| = mu N); it saturates near 1
    # because the transmitted forces are capped by the capacity. The output is smoothly clamped
    # to [-1, 2] (without vacuum the ratio is meaningless). `lost` is a held latch set by an
    # event when the lip gap exceeds `h_lost`.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
        vac::Power{Hydraulic}
    end
    @parameters begin
        L0::Real = 0.04, [unit = "m", min = 0, description = "Rest separation of the lip from the cup mount (along -z of the cup frame)"]
        A_eff::Real = 1.4e-3, [unit = "m^2", min = 0, description = "Effective suction area (holding force = A_eff * vacuum)"]
        D_lip::Real = 0.05, [unit = "m", min = 1.0e-6, description = "Lip diameter"]
        k_ax::Real = 5000.0, [unit = "N/m", min = 1.0e-9, description = "Bellows axial stiffness"]
        d_ax::Real = 15.0, [unit = "N*s/m", min = 0, description = "Bellows axial damping"]
        k_lat::Real = 2500.0, [unit = "N/m", min = 1.0e-9, description = "Bellows lateral stiffness"]
        d_lat::Real = 8.0, [unit = "N*s/m", min = 0, description = "Bellows lateral damping"]
        k_tilt::Real = 3.0, [unit = "N*m/rad", min = 0, description = "Bellows bending (tilt) stiffness"]
        k_tor::Real = 5.0, [unit = "N*m/rad", min = 0, description = "Bellows torsional stiffness"]
        d_rot::Real = 0.01, [unit = "N*m*s/rad", min = 0, description = "Bellows rotational damping"]
        mu::Real = 0.5, [unit = "1", min = 1.0e-6, description = "Lip friction coefficient on the part surface"]
        V::Real = 2.0e-5, [unit = "m^3", min = 1.0e-12, description = "Cup chamber volume"]
        perm::Real = 0.0, [unit = "m/(s*Pa)", min = 0, description = "Air permeance of the part under the cup: Q_por = perm * A_eff * vacuum"]
        A_lip0::Real = 3.0e-8, [unit = "m^2", min = 0, description = "Leak area of the sealed lip (surface roughness)"]
        Cd::Real = 0.6, [unit = "1", min = 0, description = "Discharge coefficient of the lip leak"]
        rho::Real = 1.2, [unit = "kg/m^3", min = 1.0e-12, description = "Air density (free air)"]
        p_atm::Real = 101325.0, [unit = "Pa", min = 1.0, description = "Atmospheric pressure (free-air reference of the flows)"]
        p_tr::Real = 500.0, [unit = "Pa", min = 1.0e-6, description = "Transition pressure of the regularised leak law"]
        h_ref::Real = 5.0e-4, [unit = "m", min = 1.0e-9, description = "Lift at which the transmitted bellows moment has halved"]
        h_lost::Real = 2.0e-3, [unit = "m", min = 0, description = "Lip gap that sets the `lost` latch"]
        F_min::Real = 0.5, [unit = "N", min = 1.0e-9, description = "Residual friction capacity (keeps the slip law regular without vacuum)"]
        F_eps::Real = 0.1, [unit = "N", min = 1.0e-9, description = "Smoothing force of the capacity limit"]
        v_eps::Real = 1.0e-4, [unit = "m/s", min = 1.0e-12, description = "Smoothing velocity of the slip law"]
        p_eps::Real = 1.0, [unit = "Pa", min = 1.0e-9, description = "Smoothing pressure of the vacuum level"]
        h_eps::Real = 1.0e-6, [unit = "m", min = 1.0e-12, description = "Smoothing length of the lip gap (and of the bottoming stroke)"]
        k_bot::Real = 0.0, [unit = "N/m", min = 0, description = "Bottoming stiffness scale beyond the compression stroke (0 = no bottoming)"]
        s_bot::Real = 0.01, [unit = "m", min = 0, description = "Compression stroke of the bellows before it bottoms"]
        n_bot::Real = 3.0, [unit = "1", min = 1, description = "Bottoming exponent: F_bot = k_bot xb (xb/x_bot)^(n_bot-1)"]
        x_bot::Real = 1.0e-3, [unit = "m", min = 1.0e-9, description = "Reference over-stroke of the bottoming law"]
        A_fold::Real = 0.0, [unit = "m^2", min = 0, description = "Folded annulus on which the vacuum contracts the bellows (lift stroke; 0 = none)"]
        c_vac::Real = 0.0, [unit = "1", min = 0, description = "Rise of the lateral/tilt stiffness with the vacuum: factor 1 + c_vac dp/p_atm"]
        c_ext::Real = 0.0, [unit = "1", description = "Stroke dependence of the lateral/tilt stiffness: factor exp(-c_ext ext/L0)"]
    end
    @variables begin
        rx::Real = 0.0, [unit = "m", state = :prefer, description = "Part point x in the cup frame"]
        ry::Real = 0.0, [unit = "m", state = :prefer, description = "Part point y in the cup frame"]
        rz::Real = -0.04, [unit = "m", state = :prefer, description = "Part point z in the cup frame (start -L0)"]
        qw::Real = 1.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion (point frame in cup frame)"]
        qx::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion x"]
        qy::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion y"]
        qz::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion z"]
        ex::Real = 0.0, [unit = "m", state = :prefer, description = "Elastic lateral bellows deflection x (cup frame)"]
        ey::Real = 0.0, [unit = "m", state = :prefer, description = "Elastic lateral bellows deflection y (cup frame)"]
        p::Real = 0.0, [unit = "Pa", state = :prefer, description = "Chamber gauge pressure (negative = vacuum)"]
        lost::Real = 0.0, [unit = "1", description = "Seal-lost latch (0, then 1 once the lip gap exceeded h_lost)"]
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the point frame in the cup frame"]
        wpx::Real = 0.0, [unit = "rad/s", description = "Cup angular velocity x (cup frame)"]
        wpy::Real = 0.0, [unit = "rad/s", description = "Cup angular velocity y (cup frame)"]
        wpz::Real = 0.0, [unit = "rad/s", description = "Cup angular velocity z (cup frame)"]
        ux::Real = 0.0, [unit = "m/s", description = "Velocity of the cup-frame point at r, x"]
        uy::Real = 0.0, [unit = "m/s", description = "Velocity of the cup-frame point at r, y"]
        uz::Real = 0.0, [unit = "m/s", description = "Velocity of the cup-frame point at r, z"]
        rdx::Real = 0.0, [unit = "m/s", description = "Relative velocity of the part point, x (cup frame)"]
        rdy::Real = 0.0, [unit = "m/s", description = "Relative velocity of the part point, y (cup frame)"]
        rdz::Real = 0.0, [unit = "m/s", description = "Relative velocity of the part point, z (cup frame)"]
        wrx::Real = 0.0, [unit = "rad/s", description = "Relative angular velocity x (point frame)"]
        wry::Real = 0.0, [unit = "rad/s", description = "Relative angular velocity y (point frame)"]
        wrz::Real = 0.0, [unit = "rad/s", description = "Relative angular velocity z (point frame)"]
        Fs::Real = 0.0, [unit = "N", description = "Bellows axial force without the seal limit (pull > 0)"]
        Mbx::Real = 0.0, [unit = "N*m", description = "Bellows restoring moment x (point frame)"]
        Mby::Real = 0.0, [unit = "N*m", description = "Bellows restoring moment y (point frame)"]
        Mbz::Real = 0.0, [unit = "N*m", description = "Bellows restoring moment z (point frame)"]
        Mbt::Real = 0.0, [unit = "N*m", description = "Bellows tilting moment magnitude"]
        chi::Real = 1.0, [unit = "1", description = "Moment transmission factor of a lifting lip"]
        Fc::Real = 1.0, [unit = "N", description = "Friction capacity mu N + F_min"]
        vn::Real = 1.0e-4, [unit = "m/s", description = "Smoothed lateral relative speed"]
        rhox::Real = 0.0, [unit = "1", description = "Lateral load ratio x"]
        rhoy::Real = 0.0, [unit = "1", description = "Lateral load ratio y"]
        rho4::Real = 0.0, [unit = "1", description = "|rho|^4"]
        gs::Real = 0.0, [unit = "1", description = "Slip factor |rho|^4 / (1 + |rho|^4/100)"]
        dex::Real = 0.0, [unit = "m/s", description = "Rate of the lateral deflection x"]
        dey::Real = 0.0, [unit = "m/s", description = "Rate of the lateral deflection y"]
        Flx::Real = 0.0, [unit = "N", description = "Bellows lateral restoring force x (cup frame)"]
        Fly::Real = 0.0, [unit = "N", description = "Bellows lateral restoring force y (cup frame)"]
        Fpz::Real = 0.0, [unit = "N", description = "Axial force on the part (cup frame z)"]
        tcx::Real = 0.0, [unit = "N*m", description = "Moment on the part x (point frame)"]
        tcy::Real = 0.0, [unit = "N*m", description = "Moment on the part y (point frame)"]
        tcz::Real = 0.0, [unit = "N*m", description = "Moment on the part z (point frame)"]
        A_lip::Real = 3.0e-8, [unit = "m^2", description = "Lip leak area"]
        Ur::Real = 0.0, [unit = "1", description = "Unclamped utilisation"]
        Uh::Real = 0.0, [unit = "1", description = "Utilisation clamped from above at 2"]
        xb::Real = 0.0, [unit = "m", description = "Over-stroke beyond the bottoming stroke, pos(-ext - s_bot)"]
        F_bot::Real = 0.0, [unit = "N", description = "Bottoming push of the stacked folds"]
        kf::Real = 1.0, [unit = "1", description = "Lateral/tilt stiffness factor (vacuum and stroke)"]
    end
    @outputs begin
        T::Real, [unit = "N", description = "Axial force transmitted to the part (pull > 0, push < 0)"]
        F_lat::Real, [unit = "N", description = "Lateral (shear) force on the cup"]
        M_tilt::Real, [unit = "N*m", description = "Tilting moment transmitted by the bellows"]
        Fcap::Real, [unit = "N", description = "Holding force of the seal, A_eff * vacuum"]
        N_lip::Real, [unit = "N", description = "Lip contact force, Fcap - T"]
        dp::Real, [unit = "Pa", description = "Vacuum level (atmosphere minus chamber pressure)"]
        U::Real, [unit = "1", description = "Utilisation (T + 4 M/D_lip + F_lat/mu) / Fcap: 1 = pull-off, peel or slip"]
        h::Real, [unit = "m", description = "Lip lift (gap) under an excess pull or tilting moment"]
        ext::Real, [unit = "m", description = "Bellows axial extension s - L0"]
        Q_leak::Real, [unit = "m^3/s", description = "Free-air leak flow at the lip into the cup"]
        Q_por::Real, [unit = "m^3/s", description = "Free-air flow through the porous part into the cup"]
        Q_vac::Real, [unit = "m^3/s", description = "Free-air flow drawn out of the cup by the vacuum line"]
        sealed::Real, [unit = "1", description = "1 while the seal holds, 0 once the latch `lost` is set"]
    end
    @equations begin
        s ~ qw * qw + qx * qx + qy * qy + qz * qz
        R[1, 1] ~ (qw * qw + qx * qx - qy * qy - qz * qz) / s
        R[1, 2] ~ 2 * (qx * qy - qw * qz) / s
        R[1, 3] ~ 2 * (qx * qz + qw * qy) / s
        R[2, 1] ~ 2 * (qx * qy + qw * qz) / s
        R[2, 2] ~ (qw * qw - qx * qx + qy * qy - qz * qz) / s
        R[2, 3] ~ 2 * (qy * qz - qw * qx) / s
        R[3, 1] ~ 2 * (qx * qz - qw * qy) / s
        R[3, 2] ~ 2 * (qy * qz + qw * qx) / s
        R[3, 3] ~ (qw * qw - qx * qx - qy * qy + qz * qz) / s
        # Frame twists: the port flows are the negative twists (neutral mounts, cup on side a).
        wpx ~ -a.f[1]
        wpy ~ -a.f[2]
        wpz ~ -a.f[3]
        ux ~ -a.f[4] + (wpy * rz - wpz * ry)
        uy ~ -a.f[5] + (wpz * rx - wpx * rz)
        uz ~ -a.f[6] + (wpx * ry - wpy * rx)
        rdx ~ -(R[1, 1] * b.f[4] + R[1, 2] * b.f[5] + R[1, 3] * b.f[6]) - ux
        rdy ~ -(R[2, 1] * b.f[4] + R[2, 2] * b.f[5] + R[2, 3] * b.f[6]) - uy
        rdz ~ -(R[3, 1] * b.f[4] + R[3, 2] * b.f[5] + R[3, 3] * b.f[6]) - uz
        wrx ~ -b.f[1] - (R[1, 1] * wpx + R[2, 1] * wpy + R[3, 1] * wpz)
        wry ~ -b.f[2] - (R[1, 2] * wpx + R[2, 2] * wpy + R[3, 2] * wpz)
        wrz ~ -b.f[3] - (R[1, 3] * wpx + R[2, 3] * wpy + R[3, 3] * wpz)
        ddt(rx) ~ rdx
        ddt(ry) ~ rdy
        ddt(rz) ~ rdz
        ddt(qw) ~ -0.5 * (wrx * qx + wry * qy + wrz * qz)
        ddt(qx) ~ 0.5 * (wrx * qw + wrz * qy - wry * qz)
        ddt(qy) ~ 0.5 * (wry * qw + wrx * qz - wrz * qx)
        ddt(qz) ~ 0.5 * (wrz * qw + wry * qx - wrx * qy)
        # Seal and bellows.
        dp ~ 0.5 * (-p + sqrt(p * p + p_eps * p_eps))
        Fcap ~ A_eff * dp
        ext ~ -rz - L0
        xb ~ 0.5 * ((-ext - s_bot) + sqrt((-ext - s_bot) * (-ext - s_bot) + h_eps * h_eps))
        F_bot ~ k_bot * xb * (xb / x_bot)^(n_bot - 1)
        Fs ~ k_ax * ext - d_ax * rdz + A_fold * dp - F_bot
        kf ~ (1 + c_vac * dp / p_atm) * exp(-c_ext * ext / L0)
        Mbx ~ 2 * qw * k_tilt * kf * qx + d_rot * wrx
        Mby ~ 2 * qw * k_tilt * kf * qy + d_rot * wry
        Mbz ~ 2 * qw * k_tor * qz + d_rot * wrz
        Mbt ~ sqrt(Mbx * Mbx + Mby * Mby + 1.0e-12 * k_tilt * k_tilt)
        h ~ 0.5 * ((Fs + 4 * Mbt / D_lip - Fcap) / k_ax +
                   sqrt(((Fs + 4 * Mbt / D_lip - Fcap) / k_ax)^2 + h_eps * h_eps))
        T ~ 0.5 * (Fs + Fcap - sqrt((Fs - Fcap) * (Fs - Fcap) + F_eps * F_eps))
        N_lip ~ Fcap - T
        chi ~ 1 / (1 + (h / h_ref)^2)
        M_tilt ~ chi * Mbt
        # Lateral: Dahl-type slip of the lip at the friction capacity.
        Fc ~ mu * N_lip + F_min
        vn ~ sqrt(rdx * rdx + rdy * rdy + v_eps * v_eps)
        rhox ~ k_lat * kf * ex / Fc
        rhoy ~ k_lat * kf * ey / Fc
        rho4 ~ (rhox * rhox + rhoy * rhoy)^2
        gs ~ rho4 / (1 + 0.01 * rho4)
        dex ~ rdx - vn * rhox * gs
        dey ~ rdy - vn * rhoy * gs
        ddt(ex) ~ dex
        ddt(ey) ~ dey
        Flx ~ k_lat * kf * ex + d_lat * dex
        Fly ~ k_lat * kf * ey + d_lat * dey
        F_lat ~ sqrt(Flx * Flx + Fly * Fly)
        Ur ~ (T + 4 * M_tilt / D_lip + F_lat / mu) / (Fcap + F_eps)
        Uh ~ 2 - 0.5 * (2 - Ur + sqrt((2 - Ur) * (2 - Ur) + 1.0e-6))
        U ~ -1 + 0.5 * (Uh + 1 + sqrt((Uh + 1) * (Uh + 1) + 1.0e-6))
        # Wrench on the part: force (-Flx, -Fly, T) in the cup frame at the point, moment
        # -chi Mb in the point frame; the gripper gets the opposite, moved to the cup origin.
        Fpz ~ T
        tcx ~ -chi * Mbx
        tcy ~ -chi * Mby
        tcz ~ -chi * Mbz
        b.e[1] ~ tcx
        b.e[2] ~ tcy
        b.e[3] ~ tcz
        b.e[4] ~ -R[1, 1] * Flx - R[2, 1] * Fly + R[3, 1] * Fpz
        b.e[5] ~ -R[1, 2] * Flx - R[2, 2] * Fly + R[3, 2] * Fpz
        b.e[6] ~ -R[1, 3] * Flx - R[2, 3] * Fly + R[3, 3] * Fpz
        a.e[1] ~ -(R[1, 1] * tcx + R[1, 2] * tcy + R[1, 3] * tcz) - (ry * Fpz + rz * Fly)
        a.e[2] ~ -(R[2, 1] * tcx + R[2, 2] * tcy + R[2, 3] * tcz) - (-rz * Flx - rx * Fpz)
        a.e[3] ~ -(R[3, 1] * tcx + R[3, 2] * tcy + R[3, 3] * tcz) - (-rx * Fly + ry * Flx)
        a.e[4] ~ Flx
        a.e[5] ~ Fly
        a.e[6] ~ -Fpz
        # Vacuum chamber.
        A_lip ~ A_lip0 + 3.141592653589793 * D_lip * h
        Q_leak ~ Cd * A_lip * (-p) * sqrt(2 / (rho * sqrt(p * p + p_tr * p_tr)))
        Q_por ~ perm * A_eff * dp
        Q_vac ~ -vac.f
        ddt(p) ~ p_atm * (Q_leak + Q_por + vac.f) / V
        vac.e ~ p
        ddt(lost) ~ 0.0
        sealed ~ 1 - lost
    end
    @events begin
        h > h_lost => begin
            reinit(lost, 1.0)
        end
    end
    @causality begin
        a => :effort_out
        b => :effort_out
        vac => :effort_out
    end
end
