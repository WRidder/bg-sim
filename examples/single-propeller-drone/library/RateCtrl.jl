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
    # On the ground (`ground` = 1, the touchdown latch) the loop only damps: the rate set-point
    # is zero and the integral is cleared, so it brakes any rocking of the body on its feet but
    # never pushes against them (an attitude or integral term would lean on the feet with the
    # attitude estimate's error and lift the lightly loaded ones).
    @inputs begin
        w_sp::Vec{2}, [unit = "rad/s", description = "Roll/pitch rate set-point"]
        w::Vec{3}, [unit = "rad/s", description = "Estimated body rates"]
        w_rot::Real, [unit = "rad/s", description = "Measured rotor speed"]
        armed::Real
        ground::Real, [description = "1 on the ground: rate damping only"]
    end
    @outputs tau::Vec{2} = [0.0, 0.0]
    @parameters begin
        Kp::Real = 0.29, [unit = "N*m*s/rad", description = "Proportional gain"]
        Ki::Real = 1.46, [unit = "N*m/rad", description = "Integral gain"]
        Ja::Real = 3.5e-4, [unit = "kg*m^2", min = 0, description = "Rotor spin inertia (the controller's value)"]
        k_gyro::Real = 1.0, [description = "Gyroscopic feed-forward on (1) or off (0)"]
        tau_max::Real = 0.2, [unit = "N*m", min = 0, description = "Moment limit (magnitude)"]
        i_max::Real = 0.05, [unit = "N*m", description = "Integral limit per axis"]
    end
    @variables I::Vec{2} = [0.0, 0.0], [description = "Integral state"]
    @discrete Ts = 2.5e-3 begin
        h = Ja * w_rot
        fl = ifelse(ground > 0.5, 0.0, 1.0)
        e1 = fl * w_sp[1] - w[1]
        e2 = fl * w_sp[2] - w[2]
        i1 = fl * clamp(I[1] + Ki * e1 * Ts, -i_max, i_max)
        i2 = fl * clamp(I[2] + Ki * e2 * Ts, -i_max, i_max)
        u1 = Kp * e1 + i1 + k_gyro * h * w[2]
        u2 = Kp * e2 + i2 - k_gyro * h * w[1]
        un = sqrt(u1 * u1 + u2 * u2)
        if un > tau_max
            if u1 * e1 > 0.0
                i1 = I[1]
            end
            if u2 * e2 > 0.0
                i2 = I[2]
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
