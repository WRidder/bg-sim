@block CubeLQR begin
    # 2 ms discrete state feedback for the corner-balanced cube (plan 9.9), sampled firmware (D28).
    #
    # The controller measures the body orientation (the first four entries of the pose chart,
    # a quaternion), the body rates `omega` and the wheel rates `wheel` relative to the body, and
    # forms the reduced state of design/design.py
    #
    #   z = [tilt1, tilt2, omega1..3, wheel1..3],   tilt_k = e_k . up_b,   up_b = R(q)' [0, 0, 1]
    #
    # where e1 = (1, -1, 0)/sqrt 2 and e2 = (1, 1, -2)/sqrt 6 span the plane perpendicular to the
    # equilibrium diagonal n0 = (1, 1, 1)/sqrt 3. `up_b` is the third row of R(q), so the tilt needs
    # no trigonometry. The law is u = clamp(-K z, +-u_max), the voltages of the three wheel motors;
    # the parameters hold the gain matrix K (3 x 8) that design/design.py writes verbatim.
    # The firmware samples at 2 ms and holds `u` until the next tick; the declared 0 V output is
    # held before the first sample.
    @parameters begin
        K::Mat{3,8} = [0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0; 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0; 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0], [description = "Feedback gain, u = -K z"]
        u_max::Real = 12.0, [unit = "V", min = 0, description = "Voltage limit per motor"]
    end
    @inputs begin
        pose::Vec{7}
        omega::Vec{3}
        wheel::Vec{3}
    end
    @outputs begin
        u1::Real = 0.0, [unit = "V"]
        u2::Real = 0.0, [unit = "V"]
        u3::Real = 0.0, [unit = "V"]
    end
    @discrete Ts = 2e-3 begin
        r31 = 2 * (pose[2] * pose[4] - pose[1] * pose[3])
        r32 = 2 * (pose[3] * pose[4] + pose[1] * pose[2])
        r33 = pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]
        z = [
            0.7071067811865476 * (r31 - r32),
            0.4082482904638631 * (r31 + r32 - 2 * r33),
            omega[1],
            omega[2],
            omega[3],
            wheel[1],
            wheel[2],
            wheel[3],
        ]
        v = -(K * z)
        u1 = clamp(v[1], -u_max, u_max)
        u2 = clamp(v[2], -u_max, u_max)
        u3 = clamp(v[3], -u_max, u_max)
    end
end
