@block ALDriveLoop begin
    # The drive's motion layer (DS402 over EtherCAT), sampled at 4 kHz (the 250 us internal
    # sampling time of the Synapticon EtherCAT guide):
    #
    #   mode 0  CST, cyclic synchronous torque: the target torque tau_cmd (N m at the output) is
    #           passed to the current loop, i_ref = tau_cmd / (N kt_q)
    #   mode 1  CSV, cyclic synchronous velocity: a PI on the output speed estimated from the motor
    #           encoder, w = (theta_m(k) - theta_m(k-1)) / (N Ts); the integrator is clamped to the
    #           torque limit (the speed estimate is computed in CSV only; in CST w_est stays 0)
    #
    # The q-current reference is clamped to iq_max (the max. acceleration torque of the datasheet,
    # the end of the current-torque linearity). kt_q is the torque constant per ampere of q-current
    # amplitude (kt_rms / sqrt(2)).
    @constants sample_period::Real = 2.5e-4, [unit = "s", description = "Loop period"]
    @inputs begin
        tau_cmd::Real, [unit = "N*m", description = "Target torque (CST)"]
        w_cmd::Real, [unit = "rad/s", description = "Target output speed (CSV)"]
        thm::Real, [unit = "rad", description = "Motor encoder angle (motor shaft)"]
    end
    @outputs begin
        iref::Real = 0.0, [unit = "A", description = "q current reference"]
        tau_ref::Real = 0.0, [unit = "N*m", description = "Torque reference at the output"]
        w_est::Real = 0.0, [unit = "rad/s", description = "Output speed from the motor encoder"]
    end
    @parameters begin
        mode::Real = 0.0, [description = "0 CST (torque), 1 CSV (velocity)"]
        N::Real = 7.75, [description = "Gear ratio"]
        kt_q::Real = 0.1106, [unit = "N*m/A", description = "Torque constant per A of q-current amplitude (motor side)"]
        iq_max::Real = 19.83, [unit = "A", min = 0, description = "q current limit"]
        kp_w::Real = 5.0, [unit = "N*m*s/rad", description = "CSV proportional gain"]
        ki_w::Real = 100.0, [unit = "N*m/rad", description = "CSV integral gain"]
    end
    @variables begin
        thp::Real = 0.0, [unit = "rad", description = "Output angle at the last tick"]
        wi::Real = 0.0, [unit = "N*m", description = "Velocity integrator"]
        init::Real = 0.0, [description = "1 after the first tick"]
    end
    @discrete Ts = sample_period begin
        th = thm / N
        w = 0.0
        if init > 0.5 && mode > 0.5
            w = (th - thp) / Ts
        end
        thp = th
        init = 1.0
        tlim = iq_max * N * kt_q
        tau = tau_cmd
        if mode > 0.5
            e = w_cmd - w
            tau = kp_w * e + wi
            wi = clamp(wi + ki_w * Ts * e, -tlim, tlim)
        end
        iref = clamp(tau / (N * kt_q), -iq_max, iq_max)
        tau_ref = iref * N * kt_q
        w_est = w
    end
end
