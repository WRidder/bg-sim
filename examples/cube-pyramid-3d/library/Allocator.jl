@block Allocator begin
    # 1 ms wheel-torque allocator for the four-wheel pyramid with a per-wheel torque limit
    # (X-MB5), sampled firmware (D28). Same geometry as the X-MB4 allocator.
    #
    # Wheel k has the unit axis a_k = (sin b cos f_k, sin b sin f_k, cos b), f_k = 0, 90, 180,
    # 270 deg, so A = [a_1 a_2 a_3 a_4] (3 x 4) has A A^T = diag(2 sin^2 b, 2 sin^2 b, 4 cos^2 b).
    # A motor torque tau_k on wheel k puts the reaction -tau_k a_k on the body, so the body
    # torque is T = -A tau. The firmware commands the wanted body torque `T_des` with the
    # minimum-norm solution plus a free null-space component:
    #
    #   tau = -A^+ T_des + lam n,     A^+ = A^T (A A^T)^-1,     n = (1, -1, 1, -1) / 2,   A n = 0
    #
    # Torque limit: no wheel may exceed `tau_max`. The null-space request keeps its share
    # (`|lam| / 2` of every wheel) and the body-torque request is scaled by a common factor
    # `sc <= 1` (output `sat`; 1 = unsaturated) so the largest minimum-norm torque fits in
    # the rest. The direction of the body torque is therefore preserved and the null-space
    # component stays exactly `lam`.
    #
    # Taps: `Tbx/Tby/Tbz` is the body torque -A tau the sampled command realises, `nsp` is the
    # null-space component n . tau (it equals `lam`). Outputs `i1..i4` are the motor current
    # references, `i_k = tau_k / k_t` (never above `tau_max / k_t`).
    @parameters begin
        beta::Real = 0.9553166181245093, [unit = "rad", description = "Wheel axis tilt from the body z axis"]
        k_t::Real = 0.1, [unit = "N*m/A", min = 1.0e-9, description = "Motor torque constant"]
        tau_max::Real = 1.0, [unit = "N*m", min = 1.0e-9, description = "Largest motor torque of one wheel"]
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
        sat::Real = 1.0
    end
    @discrete Ts = 1e-3 begin
        sb = sin(beta)
        cb = cos(beta)
        ux = -Tx / (2 * sb * sb)
        uy = -Ty / (2 * sb * sb)
        uz = -Tz / (4 * cb * cb)
        m1 = sb * ux + cb * uz
        m2 = sb * uy + cb * uz
        m3 = -sb * ux + cb * uz
        m4 = -sb * uy + cb * uz
        mx = max(max(abs(m1), abs(m2)), max(abs(m3), abs(m4)))
        room = tau_max - 0.5 * abs(lam)
        sc = 1.0
        if mx > room
            sc = room / mx
        end
        t1 = sc * m1 + 0.5 * lam
        t2 = sc * m2 - 0.5 * lam
        t3 = sc * m3 + 0.5 * lam
        t4 = sc * m4 - 0.5 * lam
        i1 = t1 / k_t
        i2 = t2 / k_t
        i3 = t3 / k_t
        i4 = t4 / k_t
        Tbx = -sb * (t1 - t3)
        Tby = -sb * (t2 - t4)
        Tbz = -cb * (t1 + t2 + t3 + t4)
        nsp = 0.5 * (t1 - t2 + t3 - t4)
        sat = sc
    end
end
