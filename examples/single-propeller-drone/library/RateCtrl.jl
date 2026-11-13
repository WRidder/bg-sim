@block RateCtrl begin
    # 400 Hz body-rate loop on roll and pitch (the inner loop of the cascade). The output is a
    # physical hub-moment demand (N m) for `Alloc`. The tilt plant is a gyrostat: with the rotor
    # momentum h along +z the body obeys
    #
    #   Jx p' = tau_x - h q,    Jy q' = tau_y + h p        (the torque -w x h e_z)
    #
    # so a moment about one axis mostly precesses the body about the other. The loop cancels
    # that coupling with the feed-forward w x (h e_z) = (h q, -h p), with h = Ja w_rotor from
    # the measured rotor speed, and closes a PI on what is left, a bare inertia per axis:
    #
    #   tau = Kp (w_sp - w) + I + k_gyro (h q, -h p),   I <- I + Ki (w_sp - w) Ts
    #
    # The moment vector is limited to `tau_max`, the same limit the allocation reaches
    # (kM_est A_max), and the integral is frozen while the limit is active and the error pushes
    # into it. There is no yaw channel: the vehicle has no yaw actuator.
    #
    # On the ground (`ground` = 1, the touchdown latch) the integral is zero (cleared on the first
    # ground tick and kept at zero, also while the moment limit is active), and the rate
    # set-point is scaled by `k_ground`. With k_ground = 1 the attitude loop keeps its
    # proportional authority, so the vehicle holds its lean into the wind while the thrust still
    # carries it (`PosCtrl`). Without the integral the loop pushes against the loaded feet with
    # no more than Kp K_att times the attitude error. With k_ground = 0 the loop only damps the
    # body rates; the vehicle then tips over in a wind.
    @inputs begin
        w_sp::Vec{2}, [unit = "rad/s", description = "Roll/pitch rate set-point"]
        w::Vec{3}, [unit = "rad/s", description = "Estimated body rates"]
        w_rot::Real, [unit = "rad/s", description = "Measured rotor speed"]
        armed::Real
        ground::Real, [description = "1 on the ground: no integral, set-point scaled by k_ground"]
    end
    @outputs tau::Vec{2} = [0.0, 0.0]
    @parameters begin
        Kp::Real = 0.29, [unit = "N*m*s/rad", description = "Proportional gain"]
        Ki::Real = 1.46, [unit = "N*m/rad", description = "Integral gain"]
        Ja::Real = 3.5e-4, [unit = "kg*m^2", min = 0, description = "Rotor spin inertia (the controller's value)"]
        k_gyro::Real = 1.0, [description = "Gyroscopic feed-forward on (1) or off (0)"]
        tau_max::Real = 0.2, [unit = "N*m", min = 0, description = "Moment limit (magnitude)"]
        i_max::Real = 0.05, [unit = "N*m", description = "Integral limit per axis"]
        k_ground::Real = 1.0, [min = 0, max = 1, description = "Fraction of the rate set-point kept on the ground"]
    end
    @variables I::Vec{2} = [0.0, 0.0], [description = "Integral state"]
    @discrete Ts = 2.5e-3 begin
        h = Ja * w_rot
        fl = ifelse(ground > 0.5, 0.0, 1.0)
        ks = fl + (1.0 - fl) * k_ground
        e1 = ks * w_sp[1] - w[1]
        e2 = ks * w_sp[2] - w[2]
        i1 = fl * clamp(I[1] + Ki * e1 * Ts, -i_max, i_max)
        i2 = fl * clamp(I[2] + Ki * e2 * Ts, -i_max, i_max)
        u1 = Kp * e1 + i1 + k_gyro * h * w[2]
        u2 = Kp * e2 + i2 - k_gyro * h * w[1]
        un = sqrt(u1 * u1 + u2 * u2)
        if un > tau_max
            # freeze the integral where the error pushes into the limit (on the ground: zero)
            if u1 * e1 > 0.0
                i1 = fl * I[1]
            end
            if u2 * e2 > 0.0
                i2 = fl * I[2]
            end
            u1 = Kp * e1 + i1 + k_gyro * h * w[2]
            u2 = Kp * e2 + i2 - k_gyro * h * w[1]
            un = sqrt(u1 * u1 + u2 * u2)
        end
        sc = min(1.0, tau_max / max(un, 1.0e-9))
        if armed > 0.5
            I = [i1, i2]
            tau = [u1 * sc, u2 * sc]
        else
            I = [0.0, 0.0]
            tau = [0.0, 0.0]
        end
    end
end
