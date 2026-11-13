@block RotorEsc begin
    # The moteus drive in velocity mode: a 400 Hz rotor-speed loop that produces the collective
    # motor torque. The reference is ramped with an acceleration limit (the real controller's
    # `mcout.accel_limit`), because a fast speed change kicks the body in yaw through the motor
    # reaction.
    #
    #   w_ref <- w_ref + clamp(w_cmd - w_ref, -accel_max Ts, accel_max Ts)
    #   tau_ff = kQ w_ref |w_ref| + b_m w_ref + Ja (w_ref - w_ref_old)/Ts   (drag, loss, acceleration)
    #   tau    = tau_ff + Kp (w_ref - w) + I                                 (PI, conditional integration)
    #
    # The torque limit is `tau_max - cyc_amp`: the cyclic modulation is added on top of the
    # collective torque in `CyclicDrive`, so the drive leaves headroom for it. The lower limit
    # lets the drive brake the propeller. Disarmed, the reference is zero, the integral is
    # cleared and the torque request is zero (the propeller coasts). The loop samples the
    # rotor speed, which carries the once-per-revolution ripple of the cyclic torque, so its
    # P term pushes back on that ripple. The block also samples the bus voltage for the
    # inverter duty (`v_bus_s`).
    #
    # Touchdown brake. The drive watches the landing-gear force `fc` (the peak hold of
    # `AeroWrench`, so an impact between two ticks is not missed) at its own 400 Hz. On the first
    # tick with fc > f_touch it caps the speed at `k_td` times the present speed and brakes the
    # rotor down to the cap with the reference slewing at `accel_td` (the torque limit
    # `tau_min` sets what the motor can really do). The impact lasts about 20 ms, so the brake
    # works while the feet are pressed on the ground and their friction holds the motor
    # reaction; the thrust then sits below the weight, so the rebound of the feet comes back down
    # within a short hop at a constant rotor speed. Later reductions slew at `accel_max` again.
    @inputs begin
        w_cmd::Real, [unit = "rad/s", description = "Speed command from the allocation"]
        w::Real, [unit = "rad/s", description = "Measured rotor speed"]
        armed::Real, [description = "1 = drive enabled"]
        cyc_amp::Real, [unit = "N*m", description = "Cyclic torque amplitude to reserve"]
        v_bus::Real, [unit = "V", description = "Bus voltage"]
        fc::Real, [unit = "N", description = "Landing-gear normal force (peak hold)"]
    end
    @outputs begin
        tau::Real = 0.0, [unit = "N*m", description = "Collective motor torque command"]
        w_ref::Real = 0.0, [unit = "rad/s", description = "Ramped speed reference"]
        sat::Real = 0.0, [description = "1 while the torque limit is active"]
        v_bus_s::Real = 25.2, [unit = "V", description = "Sampled bus voltage"]
        td::Real = 0.0, [description = "1 once the drive has seen the touchdown"]
        w_cap::Real = 1.0e4, [unit = "rad/s", description = "Speed cap set at touchdown"]
    end
    @parameters begin
        Kp::Real = 0.03, [unit = "N*m*s/rad", description = "Speed loop P gain"]
        Ki::Real = 0.5, [unit = "N*m/rad", description = "Speed loop I gain"]
        tau_max::Real = 1.6, [unit = "N*m", min = 0, description = "Positive torque limit"]
        tau_min::Real = -0.4, [unit = "N*m", description = "Negative (braking) torque limit"]
        accel_max::Real = 260.0, [unit = "rad/s^2", min = 0, description = "Reference acceleration limit"]
        w_idle::Real = 90.0, [unit = "rad/s", min = 0, description = "Idle speed"]
        w_max::Real = 720.0, [unit = "rad/s", min = 0, description = "Speed limit"]
        kQ::Real = 1.05e-6, [description = "Propeller drag coefficient (N m s^2/rad^2)"]
        b_m::Real = 0.0, [unit = "N*m*s/rad", description = "Viscous loss of the motor"]
        Ja::Real = 3.5e-4, [unit = "kg*m^2", description = "Rotor plus propeller inertia"]
        i_max::Real = 0.5, [unit = "N*m", description = "Integral limit"]
        f_touch::Real = 2.0, [unit = "N", description = "Landing-gear force that counts as touchdown"]
        k_td::Real = 1.0, [min = 0, max = 1, description = "Fraction of the speed kept at touchdown (1: no brake)"]
        accel_td::Real = 2000.0, [unit = "rad/s^2", min = 0, description = "Reference deceleration of the touchdown brake"]
    end
    @variables begin
        I::Real = 0.0, [unit = "N*m", description = "Integral state"]
        wr::Real = 0.0, [unit = "rad/s", description = "Ramped reference state"]
        first::Real = 0.0, [description = "1 once the reference has caught the rotor"]
    end
    @discrete Ts = 2.5e-3 begin
        v_bus_s = v_bus
        if armed > 0.5
            if first < 0.5
                # catch the rotor where it is on the first armed tick
                wr = w
                wt = w
                first = 1.0
            else
                wt = clamp(w_cmd, w_idle, w_max)
            end
            if td < 0.5 && fc > f_touch
                td = 1.0
                w_cap = k_td * w
            end
            wt = min(wt, w_cap)
            dn = ifelse(td > 0.5 && wr > w_cap, accel_td, accel_max)
            dw = clamp(wt - wr, -dn * Ts, accel_max * Ts)
            wn_ = wr + dw
            alpha = dw / Ts
            e = wn_ - w
            uff = kQ * wn_ * abs(wn_) + b_m * wn_ + Ja * alpha
            tlim = max(tau_max - cyc_amp, 0.15)
            raw = uff + Kp * e + I
            if (raw > tlim && e > 0.0) || (raw < tau_min && e < 0.0)
                I = I
            else
                I = clamp(I + Ki * e * Ts, -i_max, i_max)
            end
            raw = uff + Kp * e + I
            tau = clamp(raw, tau_min, tlim)
            sat = ifelse(raw > tlim || raw < tau_min, 1.0, 0.0)
            wr = wn_
        else
            I = 0.0
            wr = 0.0
            tau = 0.0
            sat = 0.0
            first = 0.0
            td = 0.0
            w_cap = 1.0e4
        end
        w_ref = wr
    end
end
