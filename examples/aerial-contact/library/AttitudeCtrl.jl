@block AttitudeCtrl begin
    # 250 Hz attitude loop: quaternion-error P controller (PX4 `AttitudeControl`). With the error
    # quaternion qe = conj(q) (x) qd (body frame, qe_w >= 0 picks the shorter rotation) the rate
    # set-point is w_sp = 2 K qe_v, limited per axis. The yaw gain is lower than the roll/pitch
    # gain: yaw is controlled through the weak rotor drag torque.
    @inputs begin
        q::Vec{4}
        qd::Vec{4}
        yaw_rate_ff::Real
    end
    @outputs w_sp::Vec{3} = [0.0, 0.0, 0.0]
    @parameters begin
        K_rp::Real = 6.5, [unit = "1/s", description = "Roll/pitch attitude gain"]
        K_yaw::Real = 2.8, [unit = "1/s", description = "Yaw attitude gain"]
        w_max_rp::Real = 3.5, [unit = "rad/s", description = "Roll/pitch rate limit"]
        w_max_yaw::Real = 1.6, [unit = "rad/s", description = "Yaw rate limit"]
    end
    @discrete Ts = 4e-3 begin
        e0 = q[1] * qd[1] + q[2] * qd[2] + q[3] * qd[3] + q[4] * qd[4]
        e1 = q[1] * qd[2] - q[2] * qd[1] - q[3] * qd[4] + q[4] * qd[3]
        e2 = q[1] * qd[3] + q[2] * qd[4] - q[3] * qd[1] - q[4] * qd[2]
        e3 = q[1] * qd[4] - q[2] * qd[3] + q[3] * qd[2] - q[4] * qd[1]
        sg = ifelse(e0 >= 0.0, 1.0, -1.0)
        w_sp = [
            clamp(2 * sg * K_rp * e1, -w_max_rp, w_max_rp),
            clamp(2 * sg * K_rp * e2, -w_max_rp, w_max_rp),
            clamp(2 * sg * K_yaw * e3 + yaw_rate_ff, -w_max_yaw, w_max_yaw)
        ]
    end
end
