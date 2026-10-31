@block GripController begin
    # Gripper drive controller (the usual electric-gripper scheme): a position-limited speed loop
    # with a current clamp, and a "soft grip" zone. Outside the zone the jaws travel at `v_close`
    # (closing) or `v_open` (opening) with the full current `I_max`; from `x_pre - x_band` on
    # (just before the expected part) the speed limit blends down to `v_grip` and the current
    # limit down to the GRIP CURRENT `I_grip`, over `x_band`. When the jaws meet the part the
    # speed error saturates the current at `I_grip`, so the motor torque, and through the drive
    # train the grip force, is set by the current limit. Continuous (no sampling); the blends are
    # continuous in x, so the only time switches are the command ramps.
    #
    #   cmd    = 1 from t_close to t_open (close), else 0 (open); it ramps over t_cmd, since a
    #            jump would make the clamps below switch discontinuously in time, which the
    #            event root finder cannot step past (it stalls one ulp before the jump)
    #   F_cmd  = max(F_set - ramp max(t - t_ramp, 0), 0)          grip-force setting [N per jaw]
    #   I_grip = min(F_cmd / (eta k_t G), I_max)                   current for F_cmd while driving
    #   lam    = clamp((x - x_pre) / x_band + 1, 0, 1)             0 travel ... 1 grip zone
    #   v_lim  = v_close - (v_close - v_grip) lam,   I_lim = I_max - (I_max - I_grip) lam
    #   v_ref  = clamp(Kp (cmd x_close - x), -v_open, v_lim)
    #   i_ref  = clamp(Kv (v_ref - v), -I_max, I_lim)
    #
    # `G` is the ideal jaw force per motor torque of the drive train (per jaw) and `eta` its
    # efficiency while driving, so the current for a grip force uses the forward efficiency: the
    # force a closing drive reaches. `ramp` (N/s from `t_ramp`) lowers the setting slowly for the
    # slip-threshold test.
    @inputs begin
        x::Real, [unit = "m", description = "Jaw closing travel (0 = fully open)"]
        v::Real, [unit = "m/s", description = "Jaw closing speed"]
    end
    @outputs begin
        i_ref::Real, [unit = "A", description = "Motor current reference"]
        cmd::Real, [unit = "1", description = "Gripper command: 1 close, 0 open"]
        F_cmd::Real, [unit = "N", description = "Grip-force setting per jaw"]
        I_grip::Real, [unit = "A", description = "Grip current (the current limit in the grip zone)"]
        I_lim::Real, [unit = "A", description = "Present closing current limit"]
        v_ref::Real, [unit = "m/s", description = "Jaw speed reference"]
        lam::Real, [unit = "1", description = "Grip-zone blend: 0 travelling, 1 in the grip zone"]
    end
    @parameters begin
        t_close::Real = 0.1, [unit = "s", description = "Time of the close command"]
        t_open::Real = 1.85, [unit = "s", description = "Time of the open command"]
        t_cmd::Real = 0.002, [unit = "s", min = 1.0e-6, description = "Rise time of the command (a short ramp, so that the speed reference does not jump)"]
        F_set::Real = 46.0, [unit = "N", min = 0, description = "Grip-force setting per jaw"]
        t_ramp::Real = 1.0e3, [unit = "s", description = "Start of the grip-force ramp-down (slip test)"]
        ramp::Real = 0.0, [unit = "N/s", min = 0, description = "Ramp-down rate of the grip-force setting"]
        k_t::Real = 0.012, [unit = "N*m/A", min = 1.0e-12, description = "Motor torque constant"]
        G::Real = 6283.185307179586, [unit = "1/m", min = 1.0e-12, description = "Ideal jaw force per motor torque, per jaw (N per N*m)"]
        eta::Real = 0.7, [unit = "1", min = 1.0e-6, max = 1, description = "Drive efficiency while closing (forward)"]
        I_max::Real = 2.5, [unit = "A", min = 0, description = "Motor current limit"]
        x_close::Real = 0.02, [unit = "m", description = "Closing target, beyond the part (the jaws stop on the part)"]
        v_close::Real = 0.03, [unit = "m/s", min = 0, description = "Closing (travel) speed"]
        v_grip::Real = 0.01, [unit = "m/s", min = 0, description = "Closing speed in the grip zone: the speed at which the jaws meet the part"]
        x_pre::Real = 0.0045, [unit = "m", description = "Start of the grip zone (jaw travel), just before the part"]
        x_band::Real = 0.001, [unit = "m", min = 1.0e-9, description = "Length of the blend into the grip zone"]
        v_open::Real = 0.05, [unit = "m/s", min = 0, description = "Opening speed"]
        Kp::Real = 30.0, [unit = "1/s", min = 0, description = "Position gain"]
        Kv::Real = 150.0, [unit = "A*s/m", min = 0, description = "Speed gain"]
    end
    @variables begin
        b_c::Real = 0.0, [unit = "s", description = "End of the closing ramp of the command"]
        b_o::Real = 0.0, [unit = "s", description = "End of the opening ramp of the command"]
        v_lim::Real = 0.0, [unit = "m/s", description = "Present closing speed limit"]
    end
    @equations begin
        # Each ramp end is one atom of the switch condition `t - b`, as in the motion
        # profiles, so a switch on an output-grid time is consumed in one event.
        b_c ~ 2.0 * (0.5 * t_close + 0.5 * t_cmd)
        b_o ~ 2.0 * (0.5 * t_open + 0.5 * t_cmd)
        cmd ~ ifelse(t < t_close, 0.0, ifelse(t < b_c, (t - t_close) / t_cmd,
                     ifelse(t < t_open, 1.0, ifelse(t < b_o, (b_o - t) / t_cmd, 0.0))))
        F_cmd ~ max(F_set - ramp * max(t - t_ramp, 0.0), 0.0)
        I_grip ~ min(F_cmd / (eta * k_t * G), I_max)
        lam ~ min(max((x - x_pre) / x_band + 1.0, 0.0), 1.0)
        v_lim ~ v_close - (v_close - v_grip) * lam
        I_lim ~ I_max - (I_max - I_grip) * lam
        v_ref ~ min(max(Kp * (cmd * x_close - x), -v_open), v_lim)
        i_ref ~ min(max(Kv * (v_ref - v), -I_max), I_lim)
    end
end
