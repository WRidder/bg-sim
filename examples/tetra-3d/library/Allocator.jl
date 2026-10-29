@block Allocator begin
    # 1 ms wheel-torque allocator for the four face-normal wheels of the tetrahedron (X5.6),
    # sampled firmware (D28).
    #
    # The body frame has the base face down (outward normal -z) and the apex up. Wheel j (j = 1..3)
    # sits on the side face opposite to the base vertex v_j (azimuth 90, 210, 330 deg) and wheel 4
    # on the base face, each with its spin axis along the outward face normal:
    #
    #   a1 = (0, -k, 1/3),  a2 = (c, k/2, 1/3),  a3 = (-c, k/2, 1/3),  a4 = (0, 0, -1)
    #   k = 2 sqrt 2 / 3,   c = sqrt 6 / 3                                  (unit vectors)
    #
    # With A = [a1 a2 a3 a4] (3 x 4): A A^T = 4/3 I, so A^+ = A^T (A A^T)^-1 = 3/4 A^T, and the
    # null direction is A n = 0 for n = (1, 1, 1, 1)/2 (the four face normals sum to zero).
    # A motor torque tau_k on wheel k puts the reaction -tau_k a_k on the body, so the body
    # torque is T = -A tau. The firmware commands the wanted body torque `T_des` with the
    # minimum-norm solution plus a free null-space component:
    #
    #   tau = -A^+ T_des + lam n
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
        k_t::Real = 0.1, [unit = "N*m/A", min = 1.0e-9, description = "Motor torque constant"]
        tau_max::Real = 1.6, [unit = "N*m", min = 1.0e-9, description = "Largest motor torque of one wheel"]
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
        kk = 0.9428090415820634
        cc = 0.816496580927726
        # minimum-norm torques tau = -3/4 A^T T_des
        m1 = -0.75 * (-kk * Ty + Tz / 3)
        m2 = -0.75 * (cc * Tx + 0.5 * kk * Ty + Tz / 3)
        m3 = -0.75 * (-cc * Tx + 0.5 * kk * Ty + Tz / 3)
        m4 = 0.75 * Tz
        mx = max(max(abs(m1), abs(m2)), max(abs(m3), abs(m4)))
        room = tau_max - 0.5 * abs(lam)
        sc = 1.0
        if mx > room
            sc = room / mx
        end
        t1 = sc * m1 + 0.5 * lam
        t2 = sc * m2 + 0.5 * lam
        t3 = sc * m3 + 0.5 * lam
        t4 = sc * m4 + 0.5 * lam
        i1 = t1 / k_t
        i2 = t2 / k_t
        i3 = t3 / k_t
        i4 = t4 / k_t
        Tbx = -cc * (t2 - t3)
        Tby = -(-kk * t1 + 0.5 * kk * (t2 + t3))
        Tbz = -((t1 + t2 + t3) / 3 - t4)
        nsp = 0.5 * (t1 + t2 + t3 + t4)
        sat = sc
    end
end
