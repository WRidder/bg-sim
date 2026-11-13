@block Alloc begin
    # The vehicle-specific mixer (the job of the moteus `FlightControl` in the real vehicle).
    # It receives the physical collective thrust `F` (N) and roll/pitch moment `tau` (N m) of the
    # cascade and maps them to the two actuators that exist:
    #
    #   throttle   -> rotor speed  w_cmd = sqrt(F/kT)          (velocity-mode drive)
    #   roll/pitch -> cyclic torque cx = A cos(phi), cy = A sin(phi),
    #                 A = min(|tau|/kM, A_max), phi = atan2(tau_y, tau_x) + cyc_phase
    #   yaw        -> nothing: a single propeller has no yaw authority.
    #
    # `kM` is the allocation's own, fixed estimate of the hub moment per N m of cyclic torque;
    # the plant's gain is `PropRotor.kM` (the `cyclic_gain` global), so a different plant gain
    # is a real model mismatch that the rate loop has to absorb. The cyclic torque is a
    # motor-torque amplitude (N m) that `CyclicDrive` adds to the collective torque.
    # `cyc_phase` rotates the cyclic frame: it is the azimuth calibration of the mechanism (where
    # the hinge turns acceleration into pitch, relative to the encoder zero), zero here because
    # `PropRotor` measures the azimuth from that reference. It is an angle of the rotor, not a
    # time lag.
    @inputs begin
        F::Real, [unit = "N", description = "Collective thrust command"]
        tau::Vec{2}, [unit = "N*m", description = "Roll/pitch moment command"]
        armed::Real
    end
    @outputs begin
        w_cmd::Real = 0.0, [unit = "rad/s", description = "Rotor speed command"]
        cyc_x::Real = 0.0, [unit = "N*m", description = "Cosine cyclic torque component"]
        cyc_y::Real = 0.0, [unit = "N*m", description = "Sine cyclic torque component"]
        cyc_amp::Real = 0.0, [unit = "N*m", description = "Cyclic torque amplitude"]
        sat::Real = 0.0, [description = "1 while the cyclic amplitude is limited"]
    end
    @parameters begin
        kT::Real = 4.35e-5, [min = 1.0e-9, description = "Thrust coefficient T = kT w^2"]
        kM::Real = 0.25, [min = 1.0e-9, description = "Estimated hub moment per N m of cyclic torque"]
        A_max::Real = 0.8, [unit = "N*m", min = 0, description = "Cyclic torque amplitude limit"]
        w_max::Real = 720.0, [unit = "rad/s", min = 0, description = "Rotor speed limit"]
        T_max::Real = 25.0, [unit = "N", min = 0, description = "Collective thrust limit"]
        cyc_phase::Real = 0.0, [unit = "rad", description = "Azimuth calibration of the cyclic frame"]
    end
    @discrete Ts = 2.5e-3 begin
        if armed > 0.5
            Td = clamp(F, 0.0, T_max)
            w_cmd = clamp(sqrt(Td / kT), 0.0, w_max)
            Mm = sqrt(tau[1] * tau[1] + tau[2] * tau[2])
            A = min(Mm / kM, A_max)
            Mn = Mm + 1.0e-12
            ph = atan(tau[2] / Mn, tau[1] / Mn) + cyc_phase
            cyc_x = A * cos(ph)
            cyc_y = A * sin(ph)
            cyc_amp = A
            sat = ifelse(Mm / kM > A_max, 1.0, 0.0)
        else
            w_cmd = 0.0
            cyc_x = 0.0
            cyc_y = 0.0
            cyc_amp = 0.0
            sat = 0.0
        end
    end
end
