@block SegwayCtrl begin
    # Balance, speed and heading controller of the transporter (firmware stand-in, continuous).
    #
    # Pitch plane: the LQR of `design/design.py` on the state [xi, v - v_ref, theta, theta'],
    # where xi is the integral of the speed error (the position error of the speed reference)
    # and v = r (mean joint rate + pitch rate) is the axle speed from the wheel encoders:
    #
    #     tau_c = -(K_xi xi + K_v (v - v_ref) + K_theta theta + K_w theta')      (both wheels)
    #
    # Yaw: a PD law on the heading gives the differential torque
    #
    #     tau_d = kp (psi_ref - psi) - kd psi'      (+ on the wheel at -y, - on the one at +y)
    #
    # and each wheel gets tau = clamp(tau_c / 2 +- tau_d, +-tau_max); the motor current
    # reference is tau / (n k_t). The block also reports the terminal voltage each motor would
    # need, V = R i + k_t n (joint rate), to compare with the battery bus.
    @parameters begin
        K_xi::Real = 0.0, [unit = "N*m/m", description = "LQR gain on the integral of the speed error"]
        K_v::Real = 0.0, [unit = "N*m*s/m", description = "LQR gain on the speed error"]
        K_th::Real = 0.0, [unit = "N*m/rad", description = "LQR gain on the pitch"]
        K_w::Real = 0.0, [unit = "N*m*s/rad", description = "LQR gain on the pitch rate"]
        kp_psi::Real = 0.0, [unit = "N*m/rad", description = "Heading gain"]
        kd_psi::Real = 0.0, [unit = "N*m*s/rad", description = "Yaw-rate gain"]
        tau_max::Real = 80.0, [unit = "N*m", min = 0, description = "Torque limit per wheel"]
        r::Real = 0.24, [unit = "m", min = 0, description = "Wheel radius"]
        n::Real = 24.0, [min = 0, description = "Gear ratio (motor : wheel)"]
        k_t::Real = 0.12, [unit = "N*m/A", min = 0, description = "Motor torque constant"]
        R::Real = 0.15, [unit = "Ohm", min = 0, description = "Winding resistance"]
    end
    @inputs begin
        theta::Real
        w::Real
        qd_l::Real
        qd_r::Real
        psi::Real
        wz::Real
        v_ref::Real
        psi_ref::Real
    end
    @variables begin
        xi::Real = 0.0, [unit = "m", state = :prefer, description = "Integral of the speed error"]
        tc::Real = 0.0, [unit = "N*m", description = "Total balance torque"]
        td::Real = 0.0, [unit = "N*m", description = "Differential steering torque"]
    end
    @outputs begin
        v::Real, [unit = "m/s", description = "Axle speed from the encoders"]
        tau_l::Real, [unit = "N*m", description = "Torque command of the wheel at +y"]
        tau_r::Real, [unit = "N*m", description = "Torque command of the wheel at -y"]
        i_l::Real, [unit = "A", description = "Current reference of the motor at +y"]
        i_r::Real, [unit = "A", description = "Current reference of the motor at -y"]
        vreq_l::Real, [unit = "V", description = "Voltage the motor at +y needs"]
        vreq_r::Real, [unit = "V", description = "Voltage the motor at -y needs"]
    end
    @equations begin
        v ~ r * (0.5 * (qd_l + qd_r) + w)
        ddt(xi) ~ v - v_ref
        tc ~ -(K_xi * xi + K_v * (v - v_ref) + K_th * theta + K_w * w)
        td ~ kp_psi * (psi_ref - psi) - kd_psi * wz
        tau_l ~ clamp(0.5 * tc - td, -tau_max, tau_max)
        tau_r ~ clamp(0.5 * tc + td, -tau_max, tau_max)
        i_l ~ tau_l / (n * k_t)
        i_r ~ tau_r / (n * k_t)
        vreq_l ~ R * i_l + k_t * n * qd_l
        vreq_r ~ R * i_r + k_t * n * qd_r
    end
end
