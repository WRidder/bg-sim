@block CurrentControlledDrive begin
    # Current/torque-controlled drive (J-MB11): the signal `i_ref` (A) is the armature
    # current of an ideal current source, so the motor torque is `k_t * i_ref` whatever the
    # shaft does (the winding dynamics and the back-EMF are absorbed by the ideal source).
    # The rotor inertia `J_m` and the viscous loss `b_m` sit on the shaft against the stator,
    # exactly as in `ElectricDrive`, and the joint that the shaft is bonded to carries the
    # reaction.
    #
    # Taps: `i` (A, the reference current), `w` (rad/s), `tau` (N*m, delivered to the load),
    # `tau_m` (N*m, the motor torque `k_t i_ref`) and `P_mech` (W, `tau*w`).
    @ports shaft::Power{Rotation}
    @inputs i_ref::Real, [unit = "A"]
    @outputs begin
        i::Real, [unit = "A"]
        w::Real, [unit = "rad/s"]
        tau::Real, [unit = "N*m"]
        tau_m::Real, [unit = "N*m"]
        P_mech::Real, [unit = "W"]
    end
    @parameters begin
        k_t::Real = 0.05, [unit = "N*m/A", description = "Torque constant"]
        J_m::Real = 1e-5, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        b_m::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Viscous loss of the rotor"]
    end
    @components begin
        source = CurrentSource(I = 1.0)
        ground = Ground()
        isense = CurrentSensor()
        gyrator = EMConverter(k = k_t)
        rotor = Inertia(J = J_m)
        damping = RotationalDamper(d = b_m)
        stator = FixedShaft()
        wsense = SpeedSensor()
        tsense = TorqueSensor()
        tmotor = Gain(k = k_t)
        pmech = Product()
    end
    @connections begin
        connect(source.n, isense.p)
        connect(isense.n, gyrator.n)
        connect(gyrator.p, ground.p)
        connect(source.p, ground.p)
        connect(shaft, tsense.b)
        connect(tsense.a, rotor.a)
        connect(rotor.a, gyrator.shaft)
        connect(rotor.a, damping.a)
        connect(rotor.a, wsense.a)
        connect(rotor.b, stator.a)
        connect(rotor.b, damping.b)
        connect(i_ref, source.u)
        connect(isense.y, i)
        connect(isense.y, tmotor.u)
        connect(tmotor.y, tau_m)
        connect(wsense.y, w)
        connect(tsense.y, tau)
        connect(tsense.y, pmech.u1)
        connect(wsense.y, pmech.u2)
        connect(pmech.y, P_mech)
    end
end
