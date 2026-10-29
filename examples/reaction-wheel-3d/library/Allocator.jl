@block Allocator begin
    # 1 ms wheel-torque allocator for the four-wheel pyramid (X-MB4), sampled firmware (D28).
    #
    # Wheel k has the unit axis a_k = (sin b cos f_k, sin b sin f_k, cos b), f_k = 0, 90, 180,
    # 270 deg, so the allocation matrix A = [a_1 a_2 a_3 a_4] (3 x 4) has A A^T =
    # diag(2 sin^2 b, 2 sin^2 b, 4 cos^2 b) (isotropic, 4/3 I, at the default b = atan(sqrt 2)).
    # A motor torque tau_k on wheel k puts the reaction -tau_k a_k on the body, so the body
    # torque is T = -A tau. The firmware commands the wanted body torque `T_des` with the
    # minimum-norm solution plus a free null-space component:
    #
    #   tau = -A^+ T_des + lam n,     A^+ = A^T (A A^T)^-1,     n = (1, -1, 1, -1) / 2,   A n = 0
    #
    # The null space is one-dimensional: `lam` (N m) spins the wheels against each other
    # (wheel speed bias, momentum desaturation) and never reaches the body.
    #
    # Taps: `Tbx/Tby/Tbz` is the body torque -A tau the sampled command realises (it equals
    # `T_des` at the sample), `nsp` is the null-space component n . tau (it equals `lam`).
    # Outputs `i1..i4` are the motor current references, `i_k = tau_k / k_t`.
    @parameters begin
        beta::Real = 0.9553166181245093, [unit = "rad", description = "Wheel axis tilt from the body z axis"]
        k_t::Real = 0.05, [unit = "N*m/A", min = 1.0e-9, description = "Motor torque constant"]
    end
    @inputs begin
        Tx::Real
        Ty::Real
        Tz::Real
        lam::Real
    end
    @outputs begin
        i1::Real = 0.0
        i2::Real = 0.0
        i3::Real = 0.0
        i4::Real = 0.0
        Tbx::Real = 0.0
        Tby::Real = 0.0
        Tbz::Real = 0.0
        nsp::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        sb = sin(beta)
        cb = cos(beta)
        ux = -Tx / (2 * sb * sb)
        uy = -Ty / (2 * sb * sb)
        uz = -Tz / (4 * cb * cb)
        t1 = sb * ux + cb * uz + 0.5 * lam
        t2 = sb * uy + cb * uz - 0.5 * lam
        t3 = -sb * ux + cb * uz + 0.5 * lam
        t4 = -sb * uy + cb * uz - 0.5 * lam
        i1 = t1 / k_t
        i2 = t2 / k_t
        i3 = t3 / k_t
        i4 = t4 / k_t
        Tbx = -sb * (t1 - t3)
        Tby = -sb * (t2 - t4)
        Tbz = -cb * (t1 + t2 + t3 + t4)
        nsp = 0.5 * (t1 - t2 + t3 - t4)
    end
end
