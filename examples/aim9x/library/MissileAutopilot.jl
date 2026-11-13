@block MissileAutopilot begin
    # Skid-to-turn autopilot: a roll-angle loop, a pitch/yaw **rate-command** loop and a
    # two-axis thrust-vector augmentation during the boost.
    #
    # The guidance law commands a specific force (m/s^2, up and left). For a missile in a
    # coordinated turn the body rate of that manoeuvre is
    #
    #     q_cmd = a_z_cmd / Vt,     r_left_cmd = a_y_cmd / Vt
    #
    # and a rate loop turns it into the virtual canard commands
    #
    #     dp = K_q (q_cmd - q_up),        dy = K_q (r_left_cmd - r_left)
    #
    # with r_left = -r_right. That rate is the one of the steady turn only: to *build* the
    # incidence that makes the lift, the body has to turn faster than the flight path. With the
    # rate command alone the incidence grows as the integral of (rate - a/Vt), with the
    # airframe's incidence lag T_alpha = m Vt / (qbar S CN_alpha), which is seconds for this
    # low-lift-slope body. `K_acc` adds the acceleration error to the command through a
    # lag `tau_acc`,
    #
    #     q_cmd = (a_z_cmd + x_a) / Vt,     tau_acc dx_a/dt = K_acc (a_z_cmd - a_z) - x_a,
    #
    # which shortens that lag to about T_alpha / (1 + K_acc). The lag keeps the canards' own
    # lift, which the accelerometer sees at once, out of the loop. It is 0 by default (the
    # pure rate command). The gain is scheduled on the square root of dynamic pressure:
    # the canard moment per degree grows with qbar, so the same rate command needs less
    # deflection at high qbar, and the square root keeps the loop gain roughly constant
    # without the wind-up of a 1/qbar schedule at the low-qbar end of a launch.
    #
    # Roll: `p_cmd = K_phi (phi_cmd - phi)`, `dr = K_p (p_cmd - p) + xi_r`.
    #
    # TVC: the nozzle gimbals take `tvc_gain` of the acceleration error, rate-limited and with
    # the 8 deg mechanical stop. With the motor out T is zero and the term vanishes.
    @inputs begin
        a_z_cmd::Real, [unit = "m/s^2", description = "Commanded specific force, up"]
        a_y_cmd::Real, [unit = "m/s^2", description = "Commanded specific force, left"]
        roll_cmd::Real, [unit = "rad", description = "Commanded roll angle"]
        a_z::Real, [unit = "m/s^2", description = "Measured specific force, up"]
        a_y::Real, [unit = "m/s^2", description = "Measured specific force, left"]
        p::Real, [unit = "rad/s", description = "Roll rate, right wing down"]
        q_up::Real, [unit = "rad/s", description = "Pitch rate, nose up"]
        r_right::Real, [unit = "rad/s", description = "Yaw rate, nose right"]
        phi::Real, [unit = "rad", description = "Roll angle"]
        qbar::Real, [unit = "Pa", description = "Dynamic pressure"]
        vt::Real, [unit = "m/s", description = "Airspeed"]
        T::Real, [unit = "N", description = "Motor thrust"]
        m::Real, [unit = "kg", description = "Current mass"]
        tvc_on::Real, [description = "1: thrust-vector control enabled"]
    end
    @parameters begin
        K_phi::Real = 6.0, [unit = "1/s", description = "Roll-angle loop gain"]
        K_p_roll::Real = 2.2, [description = "Roll-rate gain, deg per rad/s"]
        K_i_roll::Real = 8.0, [description = "Roll integrator, deg per rad"]
        p_cmd_max::Real = 4.363323, [unit = "rad/s", description = "Roll-rate command limit (250 deg/s)"]
        K_q::Real = 20.0, [description = "Rate-loop gain, deg per rad/s"]
        K_acc::Real = 0.0, [min = 0, description = "Acceleration-error feedback into the rate command"]
        tau_acc::Real = 0.15, [unit = "s", min = 1.0e-6, description = "Lag of the acceleration-error feedback"]
        q_cmd_max::Real = 1.5, [unit = "rad/s", description = "Pitch/yaw rate command limit"]
        dp_max::Real = 16.0, [unit = "deg", description = "Virtual pitch command limit"]
        dy_max::Real = 16.0, [unit = "deg", description = "Virtual yaw command limit"]
        dr_max::Real = 12.0, [unit = "deg", description = "Virtual roll command limit"]
        qbar_ref::Real = 150000.0, [unit = "Pa", min = 1.0, description = "Gain-scheduling reference"]
        schedule_min::Real = 0.3, [description = "Lower clamp of the qbar schedule"]
        schedule_max::Real = 1.0, [description = "Upper clamp of the qbar schedule"]
        tvc_gain::Real = 0.05, [description = "Share of the acceleration error given to the TVC"]
        tvc_min_t::Real = 1000.0, [unit = "N", min = 1.0, description = "Thrust floor in the TVC allocation"]
        tvc_max::Real = 0.1396263, [unit = "rad", description = "TVC gimbal limit (8 deg)"]
        tvc_rate::Real = 3.4906585, [description = "TVC gimbal rate limit (200 deg/s) at tau = 20 ms"]
    end
    @variables begin
        sched::Real = 1.0, [description = "Square-root qbar schedule, clamped"]
        roll_err::Real = 0.0, [unit = "rad"]
        p_cmd::Real = 0.0, [unit = "rad/s"]
        q_cmd::Real = 0.0, [unit = "rad/s"]
        r_cmd::Real = 0.0, [unit = "rad/s"]
        dr_raw::Real = 0.0, [unit = "deg"]
        dp_raw::Real = 0.0, [unit = "deg"]
        dy_raw::Real = 0.0, [unit = "deg"]
        xi_r::Real = 0.0, [unit = "deg", state = :prefer, description = "Roll integrator"]
        tp_cmd::Real = 0.0, [unit = "rad"]
        ty_cmd::Real = 0.0, [unit = "rad"]
        tp_s::Real = 0.0, [unit = "rad", state = :prefer, description = "Rate-limited TVC pitch gimbal"]
        ty_s::Real = 0.0, [unit = "rad", state = :prefer, description = "Rate-limited TVC yaw gimbal"]
        xa_z::Real = 0.0, [unit = "m/s^2", state = :prefer, description = "Filtered acceleration-error feedback, up"]
        xa_y::Real = 0.0, [unit = "m/s^2", state = :prefer, description = "Filtered acceleration-error feedback, left"]
        ez::Real = 0.0, [unit = "m/s^2"]
        ey::Real = 0.0, [unit = "m/s^2"]
    end
    @outputs begin
        dp::Real, [unit = "deg"]
        dy::Real, [unit = "deg"]
        dr::Real, [unit = "deg"]
        tvc_p::Real, [unit = "rad"]
        tvc_y::Real, [unit = "rad"]
        err_z::Real, [unit = "m/s^2"]
        err_y::Real, [unit = "m/s^2"]
        a_z_cmd_out::Real, [unit = "m/s^2"]
        a_y_cmd_out::Real, [unit = "m/s^2"]
        dp_sat::Real
        dy_sat::Real
        dr_sat::Real
        tvc_p_sat::Real
        tvc_y_sat::Real
        p_cmd_out::Real, [unit = "rad/s"]
        q_cmd_out::Real, [unit = "rad/s"]
        r_cmd_out::Real, [unit = "rad/s"]
        sched_out::Real
    end
    @equations begin
        sched ~ clamp(sqrt(max(qbar, 1000.0) / qbar_ref), schedule_min, schedule_max)
        ez ~ a_z_cmd - a_z
        ey ~ a_y_cmd - a_y
        roll_err ~ atan(sin(roll_cmd - phi), cos(roll_cmd - phi))
        p_cmd ~ clamp(K_phi * roll_err, -p_cmd_max, p_cmd_max)
        ddt(xa_z) ~ (K_acc * ez - xa_z) / tau_acc
        ddt(xa_y) ~ (K_acc * ey - xa_y) / tau_acc
        q_cmd ~ clamp((a_z_cmd + xa_z) / max(vt, 100.0), -q_cmd_max, q_cmd_max)
        r_cmd ~ clamp((a_y_cmd + xa_y) / max(vt, 100.0), -q_cmd_max, q_cmd_max)
        dr_raw ~ sched * K_p_roll * (p_cmd - p) + xi_r
        dp_raw ~ sched * K_q * (q_cmd - q_up)
        dy_raw ~ sched * K_q * (r_cmd + r_right)
        ddt(xi_r) ~ sched * K_i_roll * (p_cmd - p) + (clamp(dr_raw, -dr_max, dr_max) - dr_raw) / 0.05
        dr ~ clamp(dr_raw, -dr_max, dr_max)
        dp ~ clamp(dp_raw, -dp_max, dp_max)
        dy ~ clamp(dy_raw, -dy_max, dy_max)
        tp_cmd ~ tvc_gain * m * ez / max(T, tvc_min_t) * clamp(tvc_on, 0.0, 1.0) * clamp(T / tvc_min_t, 0.0, 1.0)
        ty_cmd ~ -tvc_gain * m * ey / max(T, tvc_min_t) * clamp(tvc_on, 0.0, 1.0) * clamp(T / tvc_min_t, 0.0, 1.0)
        ddt(tp_s) ~ clamp((tp_cmd - tp_s) / 0.02, -tvc_rate, tvc_rate)
        ddt(ty_s) ~ clamp((ty_cmd - ty_s) / 0.02, -tvc_rate, tvc_rate)
        tvc_p ~ clamp(tp_s, -tvc_max, tvc_max)
        tvc_y ~ clamp(ty_s, -tvc_max, tvc_max)
        err_z ~ ez
        err_y ~ ey
        a_z_cmd_out ~ a_z_cmd
        a_y_cmd_out ~ a_y_cmd
        dp_sat ~ ifelse(dp_raw * dp_raw > dp_max * dp_max, 1.0, 0.0)
        dy_sat ~ ifelse(dy_raw * dy_raw > dy_max * dy_max, 1.0, 0.0)
        dr_sat ~ ifelse(dr_raw * dr_raw > dr_max * dr_max, 1.0, 0.0)
        tvc_p_sat ~ ifelse(tp_s * tp_s > tvc_max * tvc_max, 1.0, 0.0)
        tvc_y_sat ~ ifelse(ty_s * ty_s > tvc_max * tvc_max, 1.0, 0.0)
        p_cmd_out ~ p_cmd
        q_cmd_out ~ q_cmd
        r_cmd_out ~ r_cmd
        sched_out ~ sched
    end
end
