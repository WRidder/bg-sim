@block RigEnergy begin
    # Energy book of the free model (a measurement: no ports, no feedback). The kinetic energy of
    # each body is 1/2 P . V (its body-frame momentum and twist, the RigidBody3D outputs P and V),
    # the potential energy m g z of its centre, plus the energy in the contact spring (`Ec` of the
    # RollingSphere) and in the two lock springs of the gimbal (k_lock (q - q0 - dq)^2 / 2 per axis; lock 1 is preloaded by the ball weight).
    # `loss` integrates the contact's dissipated power `Pd`; `Ebal = E + loss` stays constant when
    # nothing else dissipates (the lock dampers only see the tiny plate vibration).
    @inputs begin
        Pb::Vec{6}, [description = "Ball momentum (body frame)"]
        Vb::Vec{6}, [description = "Ball twist (body frame)"]
        gb::Vec{7}, [description = "Ball pose"]
        Pp::Vec{6}, [description = "Plate momentum (body frame)"]
        Vp::Vec{6}, [description = "Plate twist (body frame)"]
        gp::Vec{7}, [description = "Plate pose"]
        Ec::Real, [unit = "J", description = "Contact spring energy"]
        Pd::Real, [unit = "W", description = "Contact dissipation"]
        q1::Real, [unit = "rad", description = "Gimbal angle 1"]
        q2::Real, [unit = "rad", description = "Gimbal angle 2"]
    end
    @outputs begin
        Ek::Real, [unit = "J", description = "Kinetic energy of the ball (translation and rotation)"]
        Ekrot::Real, [unit = "J", description = "Rotational kinetic energy of the ball"]
        E::Real, [unit = "J", description = "Stored mechanical energy (ball, plate, contact and lock springs, gravity)"]
        loss::Real, [unit = "J", description = "Energy dissipated in the contact since the start"]
        Ebal::Real, [unit = "J", description = "E + loss (constant for a lossless rig)"]
    end
    @parameters begin
        mb::Real = 0.067, [unit = "kg", description = "Ball mass"]
        mp::Real = 0.87, [unit = "kg", description = "Plate mass"]
        g0::Real = 9.81, [unit = "m/s^2", description = "Gravity"]
        k_lock::Real = 1.0e4, [unit = "N*m/rad", description = "Stiffness of the gimbal locks"]
        q10::Real = 0.0, [unit = "rad", description = "Rest angle of lock 1"]
        q20::Real = 0.0, [unit = "rad", description = "Rest angle of lock 2"]
        dq1::Real = 0.0, [unit = "rad", description = "Preload of lock 1: its spring is relaxed at q1 = q10 + dq1"]
    end
    @variables begin
        W::Real = 0.0, [unit = "J", description = "Integral of Pd"]
    end
    @equations begin
        Ekrot ~ 0.5 * (Pb[1] * Vb[1] + Pb[2] * Vb[2] + Pb[3] * Vb[3])
        Ek ~ Ekrot + 0.5 * (Pb[4] * Vb[4] + Pb[5] * Vb[5] + Pb[6] * Vb[6])
        E ~ Ek + mb * g0 * gb[7] + 0.5 * (Pp[1] * Vp[1] + Pp[2] * Vp[2] + Pp[3] * Vp[3] + Pp[4] * Vp[4] + Pp[5] * Vp[5] + Pp[6] * Vp[6]) + mp * g0 * gp[7] + Ec + 0.5 * k_lock * ((q1 - q10 - dq1) * (q1 - q10 - dq1) + (q2 - q20) * (q2 - q20))
        ddt(W) ~ Pd
        loss ~ W
        Ebal ~ E + W
    end
end
