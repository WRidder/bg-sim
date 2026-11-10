@block StandControl begin
    # Test-stand controller of the rotor-stand model (the JPL 25-ft Space Simulator hover test,
    # Koning et al. 2019, and the cyclic torque steps of Grip et al. 2017), at 100 Hz:
    #
    #   thrust      a staircase of thrust-coefficient targets ct[k] from t_ct[k] on; a PI law on the
    #               symmetric collective drives the measured total thrust to ct rho A (Omega R)^2
    #               (with `k_track` = 0 the symmetric collective is the open-loop staircase th0[k])
    #   torque      a PI law on the differential collective trims the net yaw torque to zero (the
    #               coaxial pair is trimmed torque-free, as in the published hover sweeps)
    #   cyclic      steps of +-`cyc` on the lower rotor at t_cyc: cosine (pitch) then sine (roll),
    #               the sequence of Grip et al. (2017) Fig. 15 (3 s each)
    @constants W::Int = 8
    @inputs begin
        tm::Real
        T::Real, [unit = "N", description = "Measured total thrust"]
        Qu::Real, [unit = "N*m", description = "Upper rotor aerodynamic torque"]
        Ql::Real, [unit = "N*m", description = "Lower rotor aerodynamic torque"]
    end
    @outputs begin
        th_u::Real = 0.0, [unit = "rad"]
        th_l::Real = 0.0, [unit = "rad"]
        cx_l::Real = 0.0, [unit = "rad"]
        cy_l::Real = 0.0, [unit = "rad"]
        ct_sp::Real = 0.0, [description = "Thrust-coefficient target"]
    end
    @parameters begin
        rho::Real = 0.0175, [unit = "kg/m^3"]
        omega::Real = 272.27, [unit = "rad/s"]
        R::Real = 0.605, [unit = "m"]
        t_ct::Vec{W} = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0], [unit = "s", description = "Start of each thrust plateau"]
        ct::Vec{W} = [0.008, 0.0115, 0.0148, 0.0178, 0.0206, 0.0237, 0.0148, 0.0148], [description = "Thrust-coefficient target of each plateau"]
        th0::Vec{W} = [0.1, 0.13, 0.16, 0.19, 0.22, 0.25, 0.16, 0.16], [unit = "rad", description = "Open-loop symmetric collective of each plateau"]
        k_track::Real = 1.0, [description = "1: track the thrust target; 0: open-loop collective"]
        Kt::Real = 0.01, [unit = "rad/N", description = "Thrust PI proportional gain"]
        Kti::Real = 0.2, [unit = "rad/(N*s)", description = "Thrust PI integral gain"]
        Kq::Real = 0.05, [unit = "rad/(N*m)", description = "Torque-trim PI proportional gain"]
        Kqi::Real = 1.0, [unit = "rad/(N*m*s)", description = "Torque-trim PI integral gain"]
        t_cyc::Real = 99.0, [unit = "s", description = "Start of the cyclic step sequence"]
        cyc::Real = 0.0873, [unit = "rad", description = "Cyclic step amplitude (5 deg)"]
    end
    @variables begin
        it::Real = 0.0
        iq::Real = 0.0
    end
    @discrete Ts = 10e-3 begin
        c = ct[1]
        t0 = th0[1]
        for k in 2:W
            c = c + ifelse(tm >= t_ct[k], ct[k] - ct[k - 1], 0.0)
            t0 = t0 + ifelse(tm >= t_ct[k], th0[k] - th0[k - 1], 0.0)
        end
        tt = c * rho * 3.141592653589793 * R * R * (omega * R)^2
        et = tt - T
        it = it + Kti * et * Ts * k_track
        eq = Qu - Ql
        iq = iq + Kqi * eq * Ts
        ths = t0 + k_track * (Kt * et + it)
        tha = Kq * eq + iq
        th_u = ths - tha
        th_l = ths + tha
        s = tm - t_cyc
        cy_l = cyc * (ifelse(s >= 0.0 && s < 3.0, 1.0, 0.0) - ifelse(s >= 6.0 && s < 9.0, 1.0, 0.0))
        cx_l = cyc * (ifelse(s >= 12.0 && s < 15.0, 1.0, 0.0) - ifelse(s >= 18.0 && s < 21.0, 1.0, 0.0))
        ct_sp = c
    end
end
