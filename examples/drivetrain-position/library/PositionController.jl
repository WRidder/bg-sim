@block PositionController begin
    # Discrete 1 kHz firmware for the load-position servo of the compliant drivetrain. One block, four jobs:
    #   1. trajectory generator: a command step starts a septic smoothstep (zero velocity, acceleration
    #      and jerk at both ends) of duration Ttraj; it yields r, r', r'', r''' every tick;
    #   2. steady-state Kalman filter on [theta_m, w_m, theta_L, w_L, T_load] from the two encoders;
    #   3. model-inversion feedforward of the voltage along the trajectory (rod twist included);
    #   4. LQR with integral action on [delta - delta_ref, w_m - w_m_ref, w_L - r', theta_L - r, z],
    #      delta = theta_m/n - theta_L (rod twist), then clamp to +-umax with back-off of the integrator.
    # `design/design.py` rewrites the numbers between the GAINS markers; the defaults are its output.
    @constants begin
        nx::Int = 5
    end
    @parameters begin
        # ---- GAINS (written by design/design.py) ----
        Phi::Mat{nx,nx} = [0.999905410198 0.000920258597888 0.000945898022183 1.10794707533e-06 -1.73503675267e-07; -0.183985242753 0.844841891851 1.83985242753 0.00247910837846 -0.000553973537667; 2.99914192192e-05 3.323841226e-08 0.999700085808 0.000999650092006 -0.000249945843861; 0.0599723578379 7.43732513537e-05 -0.599723578379 0.999200316159 -0.499825046003; 0.0 0.0 0.0 0.0 1.0], [description = "Discrete state matrix of the design model [theta_m, w_m, theta_L, w_L, T_load] at 1 ms"]
        Bd::Vec{nx} = [0.000788421855495, 1.53376432981, 1.73503675267e-08, 5.53973537667e-05, 0.0], [description = "Discrete input vector (volts)"]
        Cm::Vec{nx} = [1.0, 0.0, 0.0, 0.0, 0.0], [description = "Motor encoder measurement vector"]
        Cl::Vec{nx} = [0.0, 0.0, 1.0, 0.0, 0.0], [description = "Load encoder measurement vector"]
        Lm::Vec{nx} = [0.0122611996076, 0.0734578467168, 0.000324892986292, -0.021057909442, 0.00279423399111], [description = "Kalman gain column of the motor encoder"]
        Ll::Vec{nx} = [0.00519828778067, 1.28225708492, 0.165993861472, 15.0170238788, -1.42879114438], [description = "Kalman gain column of the load encoder"]
        K::Vec{5} = [398.97932715, 0.210845678427, 42.944561999, 458.448092282, 646.766737458], [description = "LQR gain on [delta, w_m, w_L, theta_L error, z]"]
        gear::Real = 10.0, [description = "Gear ratio n"]
        J2::Real = 0.002, [unit = "kg*m^2", description = "Load wheel inertia"]
        Jeq::Real = 6e-05, [unit = "kg*m^2", description = "Motor-side inertia (rotor plus wheel 1 reflected)"]
        Rd::Real = 0.0001, [description = "Motor viscous damping"]
        Ksh::Real = 1.2, [unit = "N*m/rad", description = "Shaft stiffness"]
        Dsh::Real = 0.001, [unit = "N*m*s/rad", description = "Shaft damping"]
        Rm::Real = 1.0, [unit = "Ohm", description = "Armature resistance"]
        kt::Real = 0.1, [description = "Motor constant"]
        Ttraj::Real = 0.8, [unit = "s", min = 1e-3, description = "Duration of the smoothstep trajectory"]
        umax::Real = 24.0, [unit = "V", min = 0.0, description = "Voltage limit"]
        # ---- END GAINS ----
    end
    @inputs begin
        theta_m::Real
        theta_L::Real
        r_cmd::Real
    end
    @outputs begin
        u::Real = 0.0, [unit = "V"]
        r_traj::Real = 0.0, [unit = "rad", description = "Smoothed position reference"]
        theta_L_hat::Real = 0.0, [unit = "rad"]
        w_L_hat::Real = 0.0, [unit = "rad/s"]
        T_hat::Real = 0.0, [unit = "N*m", description = "Estimated load-torque disturbance"]
    end
    @variables begin
        xhat::Vec{nx} = [0.0, 0.0, 0.0, 0.0, 0.0], [description = "State estimate [theta_m, w_m, theta_L, w_L, T_load]"]
        z::Real = 0.0, [description = "Integral of the load-position error"]
        tk::Real = 0.0, [description = "Ticks since the trajectory started"]
        r0::Real = 0.0, [description = "Trajectory start"]
        r1::Real = 0.0, [description = "Trajectory target"]
        rr::Real = 0.0, [description = "Current trajectory position"]
    end
    @discrete Ts = 1e-3 begin
        if r_cmd != r1
            r0 = rr
            r1 = r_cmd
            tk = 0.0
        end
        tau = min(tk * Ts / Ttraj, 1.0)
        t2 = tau * tau
        t3 = t2 * tau
        t4 = t3 * tau
        t5 = t4 * tau
        t6 = t5 * tau
        t7 = t6 * tau
        dr = r1 - r0
        rr = r0 + dr * (35.0 * t4 - 84.0 * t5 + 70.0 * t6 - 20.0 * t7)
        rd = dr * (140.0 * t3 - 420.0 * t4 + 420.0 * t5 - 140.0 * t6) / Ttraj
        rdd = dr * (420.0 * t2 - 1680.0 * t3 + 2100.0 * t4 - 840.0 * t5) / (Ttraj * Ttraj)
        rddd = dr * (840.0 * tau - 5040.0 * t2 + 8400.0 * t3 - 4200.0 * t4) / (Ttraj * Ttraj * Ttraj)
        # Kalman measurement update, two encoders
        inn_m = theta_m - dot(Cm, xhat)
        inn_l = theta_L - dot(Cl, xhat)
        xhat = xhat + Lm * inn_m + Ll * inn_l
        z += Ts * (xhat[3] - rr)
        # feedforward: the torque in the shaft carries J2*r'' plus the estimated load torque
        tau_r = J2 * rdd + Dsh * J2 * rddd / Ksh + xhat[5]
        wm_r = gear * (rd + J2 * rddd / Ksh)
        taum = Jeq * gear * rdd + Rd * wm_r + tau_r / gear
        uff = Rm / kt * taum + kt * wm_r
        e1 = xhat[1] / gear - xhat[3] - tau_r / Ksh
        e2 = xhat[2] - wm_r
        e3 = xhat[4] - rd
        e4 = xhat[3] - rr
        v = uff - (K[1] * e1 + K[2] * e2 + K[3] * e3 + K[4] * e4 + K[5] * z)
        u = clamp(v, -umax, umax)
        if abs(v) > umax
            z -= Ts * (xhat[3] - rr)
        end
        xhat = Phi * xhat + Bd * u
        r_traj = rr
        theta_L_hat = xhat[3]
        w_L_hat = xhat[4]
        T_hat = xhat[5]
        tk += 1.0
    end
end
