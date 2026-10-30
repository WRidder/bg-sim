@block Mixer begin
    # Control allocation at 250 Hz for N rotors (a hexarotor here): collective thrust F (N) and body
    # torques tau (N m) -> N rotor thrust commands -> rotor speed commands. `Minv` (N x 4) is the
    # pseudo-inverse of the allocation matrix
    #
    #   [F, tx, ty, tz]' = M T,   M = [1; ry; -rx; -spin kQ/kT]'       (design/design.py builds it)
    #
    # The torque demand comes from two sources: `tau` from the cascaded rate controller (free flight,
    # engage, disengage) or `tau2` from the contact controller; `sel` > 0.5 picks `tau2`.
    #
    # Saturation (PX4 `ControlAllocator` style, attitude has priority over thrust): the torque part
    # of the demand is scaled down until its spread fits [Tmin, Tmax], then the collective part is
    # shifted so that the largest and the smallest rotor command fit. `sat` is 1 while either
    # reduction is active. Speed command w = sqrt(T / kT), zero while disarmed.
    @constants N::Int = 6
    @inputs begin
        F::Real
        tau::Vec{3}
        tau2::Vec{3}
        sel::Real
        armed::Real
    end
    @outputs begin
        w_cmd::Vec{N} = [534.0, 534.0, 534.0, 534.0, 534.0, 534.0], [description = "Rotor speed commands (start at the hover speed: the run starts in hover)"]
        T_cmd::Vec{N} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        sat::Real = 0.0
    end
    @parameters begin
        Minv::Mat{N,4} = [0.1667 0.0 0.0 0.0; 0.1667 0.0 0.0 0.0; 0.1667 0.0 0.0 0.0; 0.1667 0.0 0.0 0.0; 0.1667 0.0 0.0 0.0; 0.1667 0.0 0.0 0.0], [description = "Pseudo-inverse of the allocation matrix"]
        kT::Real = 1.42e-5, [description = "Thrust coefficient (N s^2/rad^2)"]
        T_min::Real = 0.5, [unit = "N", min = 0, description = "Idle thrust per rotor while armed"]
        T_max::Real = 13.0, [unit = "N", min = 0, description = "Thrust limit per rotor (78 N in total)"]
    end
    @discrete Ts = 4e-3 begin
        tu = ifelse(sel > 0.5, tau2, tau)
        tc = Minv * [F, 0.0, 0.0, 0.0]
        tq = Minv * [0.0, tu[1], tu[2], tu[3]]
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
