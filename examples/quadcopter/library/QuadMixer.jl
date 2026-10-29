@block QuadMixer begin
    # Control allocation at 500 Hz: collective thrust F (N) and body torques tau (N m) -> N
    # rotor thrust commands -> rotor speed commands. Reusable for any rotor layout: `Minv` (N x 4)
    # is the pseudo-inverse of the allocation matrix
    #
    #   [F, tx, ty, tz]' = M T,   M = [1; ry; -rx; -spin kQ/kT]'       (design/design.py builds it)
    #
    # so a hexarotor or an octorotor only changes `Minv` and N.
    #
    # Saturation (PX4 `ControlAllocator` style, attitude has priority over thrust): the torque part
    # of the demand is scaled down until its spread fits [Tmin, Tmax], then the collective part is
    # shifted so that the largest and the smallest rotor command fit. `sat` is 1 while either
    # reduction is active. Speed command w = sqrt(T / kT), zero while disarmed.
    @constants N::Int = 4
    @inputs begin
        F::Real
        tau::Vec{3}
        armed::Real
    end
    @outputs begin
        w_cmd::Vec{N} = [0.0, 0.0, 0.0, 0.0]
        T_cmd::Vec{N} = [0.0, 0.0, 0.0, 0.0]
        sat::Real = 0.0
    end
    @parameters begin
        Minv::Mat{N,4} = [0.25 0.0 -1.0 -1.0; 0.25 0.0 1.0 -1.0; 0.25 0.0 1.0 1.0; 0.25 0.0 -1.0 1.0], [description = "Pseudo-inverse of the allocation matrix"]
        kT::Real = 1.42e-5, [description = "Thrust coefficient (N s^2/rad^2)"]
        T_min::Real = 0.4, [unit = "N", min = 0, description = "Idle thrust per rotor while armed"]
        T_max::Real = 8.5, [unit = "N", min = 0, description = "Thrust limit per rotor (below the voltage limit of the drive)"]
    end
    @discrete Ts = 2e-3 begin
        tc = Minv * [F, 0.0, 0.0, 0.0]
        tq = Minv * [0.0, tau[1], tau[2], tau[3]]
        hq = tq[1]
        lq = tq[1]
        for k in 2:N
            hq = max(hq, tq[k])
            lq = min(lq, tq[k])
        end
        sc = min(1.0, (T_max - T_min) / max(hq - lq, 1.0e-9))
        tn = tc + sc * tq
        hi = tn[1]
        lo = tn[1]
        for k in 2:N
            hi = max(hi, tn[k])
            lo = min(lo, tn[k])
        end
        sh = 0.0
        if hi > T_max
            sh = T_max - hi
        end
        if lo + sh < T_min
            sh = T_min - lo
        end
        tf = tn
        for k in 1:N
            tf[k] = clamp(tn[k] + sh, T_min, T_max)
        end
        wc = tf
        for k in 1:N
            wc[k] = sqrt(tf[k] / kT)
        end
        if armed > 0.5
            T_cmd = tf
            w_cmd = wc
        else
            T_cmd = tf - tf
            w_cmd = wc - wc
        end
        sat = ifelse(armed > 0.5 && (sc < 1.0 || abs(sh) > 0.0), 1.0, 0.0)
    end
end
