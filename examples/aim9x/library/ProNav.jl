@block ProNav begin
    # Three-dimensional proportional navigation (the classic Sidewinder guidance law, in the
    # form the AIM-9X uses with its imaging seeker):
    #
    #     a = N V_c (omega_LOS x u_LOS)
    #
    # The seeker gives the inertial LOS rates in body axes; for a LOS near the body x axis the
    # two components are
    #
    #     a_z = -N V_c los_pitch,      a_y = +N V_c los_yaw
    #
    # (positive z up, positive y left). A gravity-compensation term `g0 gz_body` is added
    # because the autopilot commands *specific* force; the vector is then limited to the smaller of `a_max` and a share of the aerodynamic lift limit, and faded in after a launch transient
    # (60 g for the AIM-9X) and the lift limit.
    #
    # `t_go` is range over closing speed, for the fuze and the plots.
    @inputs begin
        los_pitch::Real, [unit = "rad/s", description = "Inertial LOS rate about body y"]
        los_yaw::Real, [unit = "rad/s", description = "Inertial LOS rate about body z"]
        range::Real, [unit = "m"]
        range_rate::Real, [unit = "m/s", description = "Closing speed, positive closing"]
        gz_body::Real, [description = "World z in body axes (R[3,3])"]
        qbar::Real, [unit = "Pa", description = "Dynamic pressure"]
        m::Real, [unit = "kg", description = "Current mass"]
    end
    @parameters begin
        N::Real = 4.0, [min = 1.0, description = "Navigation constant"]
        a_max::Real = 588.399, [unit = "m/s^2", min = 1.0e-6, description = "Acceleration limit"]
        vc_min::Real = 120.0, [unit = "m/s", min = 1.0e-6, description = "Closing-speed floor"]
        g0::Real = 9.80665, [unit = "m/s^2", description = "Gravitational acceleration"]
        gravity_comp::Real = 1.5, [description = "1: add the gravity component"]
        S_ref::Real = 0.0126678, [unit = "m^2", description = "Body reference area"]
        CN_MAX::Real = 12.0, [min = 0, description = "Lift-coefficient clamp of the airframe"]
        a_frac::Real = 0.5, [min = 0, max = 1.0, description = "Share of the aerodynamic limit used by guidance"]
        tau_g::Real = 0.12, [unit = "s", min = 1.0e-6, description = "Guidance-command lag"]
        t_lock::Real = 1.0, [unit = "s", min = 0, description = "Guidance enable time after launch"]
    end
    @variables begin
        az0::Real = 0.0, [unit = "m/s^2"]
        ay0::Real = 0.0, [unit = "m/s^2"]
        amag::Real = 0.0, [unit = "m/s^2"]
        a_lim::Real = 588.399, [unit = "m/s^2"]
        scale::Real = 1.0
        vc::Real = 120.0, [unit = "m/s"]
        enable::Real = 0.0
        az_s::Real = 0.0, [unit = "m/s^2", state = :prefer, description = "Filtered pitch command"]
        ay_s::Real = 0.0, [unit = "m/s^2", state = :prefer, description = "Filtered yaw command"]
    end
    @outputs begin
        a_z_cmd::Real, [unit = "m/s^2", description = "Commanded specific force, up"]
        a_y_cmd::Real, [unit = "m/s^2", description = "Commanded specific force, left"]
        a_cmd::Real, [unit = "m/s^2"]
        a_limit::Real, [unit = "m/s^2"]
        sat::Real
        t_go::Real, [unit = "s"]
        vc_out::Real, [unit = "m/s"]
        pn_gain::Real, [unit = "m/s", description = "N V_c of the law"]
    end
    @equations begin
        enable ~ clamp((t - t_lock) / 0.2, 0.0, 1.0)
        vc ~ max(range_rate, vc_min)
        az0 ~ -N * vc * los_pitch + g0 * gz_body * gravity_comp
        ay0 ~ N * vc * los_yaw
        amag ~ sqrt(az0 * az0 + ay0 * ay0)
        a_lim ~ min(a_max, a_frac * qbar * S_ref * CN_MAX / max(m, 1.0e-9))
        scale ~ min(1.0, a_lim / max(amag, 1.0e-9))
        a_z_cmd ~ az_s
        a_y_cmd ~ ay_s
        ddt(az_s) ~ (az0 * scale * enable - az_s) / tau_g
        ddt(ay_s) ~ (ay0 * scale * enable - ay_s) / tau_g
        a_cmd ~ sqrt(a_z_cmd * a_z_cmd + a_y_cmd * a_y_cmd)
        a_limit ~ a_lim
        sat ~ ifelse(amag * enable > a_max, 1.0, 0.0)
        t_go ~ range / vc
        vc_out ~ vc
        pn_gain ~ N * vc
    end
end
