@block AttCtrl begin
    # 250 Hz attitude loop: quaternion-error P (PX4 `AttitudeControl`) on roll and pitch only,
    # plus the tilt-rate feed-forward of the position loop:
    #
    #   w_sp = 2 K qe_v + w_ff,   qe = conj(q) (x) qd,   qe_w >= 0
    #
    # There is no yaw rate set-point: a single propeller has no yaw actuator. The desired
    # attitude is built with the measured heading, so its yaw component is the current heading;
    # the yaw part of the quaternion error is discarded. The fins decide the heading.
    @inputs begin
        q::Vec{4}
        qd::Vec{4}
        w_ff::Vec{2}, [unit = "rad/s", description = "Tilt-rate feed-forward (roll, pitch)"]
    end
    @outputs w_sp::Vec{2} = [0.0, 0.0]
    @parameters begin
        K_rp::Real = 5.0, [unit = "1/s", description = "Roll/pitch attitude gain"]
        w_max_rp::Real = 2.2, [unit = "rad/s", description = "Roll/pitch rate limit"]
    end
    @discrete Ts = 4e-3 begin
        e0 = q[1] * qd[1] + q[2] * qd[2] + q[3] * qd[3] + q[4] * qd[4]
        e1 = q[1] * qd[2] - q[2] * qd[1] - q[3] * qd[4] + q[4] * qd[3]
        e2 = q[1] * qd[3] + q[2] * qd[4] - q[3] * qd[1] - q[4] * qd[2]
        sg = ifelse(e0 >= 0.0, 1.0, -1.0)
        w_sp = [
            clamp(2 * sg * K_rp * e1 + w_ff[1], -w_max_rp, w_max_rp),
            clamp(2 * sg * K_rp * e2 + w_ff[2], -w_max_rp, w_max_rp)
        ]
    end
end
