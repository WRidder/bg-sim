@block ElectricDrive begin
    # Voltage-input DC drive as a composite of the documented electrical/rotation primitives
    # (J-MB11). The signal input `u` is the terminal voltage in volts.
    #
    #   u --> VoltageSource -- R_w -- L -- CurrentSensor -- EMConverter(k_t) -- ground
    #                                                         |
    #   shaft --- TorqueSensor --- node ---+--- Inertia(J_m) --- fixed stator
    #                                      +--- RotationalDamper(b_m) --- fixed stator
    #                                      +--- SpeedSensor
    #
    # The stator is the frame of the shaft flow: the shaft rate is the rate relative to the
    # stator, exactly the `drive` rate of a planar joint (`Revolute2D*`, rate `qdot`), and the
    # **joint carries the reaction** (the reaction torque on the joint's parent is the joint's
    # own `parent` effort). A drive whose stator is itself free to rotate needs the housing
    # reaction explicitly: use `ReactionWheel` (STATUS NOTE-8: `EMConverter` has no housing
    # port, so this composite fixes the stator instead of faking one).
    #
    # Taps: `i` (A), `w` (rad/s, shaft rate), `tau` (N*m, torque delivered to the load at the
    # shaft, positive when it drives the shaft in the positive direction), `P_el` (W,
    # `u*i`) and `P_mech` (W, `tau*w`). Losses are `R_w i^2 + b_m w^2`; stored energies are
    # `L i^2 / 2` and `J_m w^2 / 2`.
    #
    # Recording: composite outputs are aliases of the inner signals, so the run columns are
    # `<drive>/isense/y` (i), `wsense/y` (w), `tsense/y` (tau), `pel/y`, `pmech/y`.
    #
    # Causality: the shaft flow is imposed by whatever the shaft is bonded to, so a rotor
    # inertia `J_m` rigidly bonded to another inertia (a locked shaft, a joint that imposes
    # the rate, a gearbox into a load inertia) is a derivative-causal pair: MTK reduces the
    # index and reports W201. Put an `ElasticShaft` between drive and joint (as the J-MB12
    # joint test does) to keep every storage element integral.
    @ports shaft::Power{Rotation}
    @inputs u::Real, [unit = "V"]
    @outputs begin
        i::Real, [unit = "A"]
        w::Real, [unit = "rad/s"]
        tau::Real, [unit = "N*m"]
        P_el::Real, [unit = "W"]
        P_mech::Real, [unit = "W"]
    end
    @parameters begin
        R_w::Real = 2.0, [unit = "Ohm", min = 0, description = "Armature resistance"]
        L::Real = 5e-4, [unit = "H", min = 0, description = "Armature inductance"]
        k_t::Real = 0.05, [unit = "N*m/A", description = "Torque and back-EMF constant"]
        J_m::Real = 1e-5, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        b_m::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Viscous loss of the rotor"]
    end
    @components begin
        source = VoltageSource(V = 1.0)
        ground = Ground()
        resistor = Resistor(R = R_w)
        inductor = Inductor(L = L)
        isense = CurrentSensor()
        gyrator = EMConverter(k = k_t)
        rotor = Inertia(J = J_m)
        damping = RotationalDamper(d = b_m)
        stator = FixedShaft()
        wsense = SpeedSensor()
        tsense = TorqueSensor()
        uin = Gain(k = 1.0)
        pel = Product()
        pmech = Product()
    end
    @connections begin
        connect(source.p, resistor.p)
        connect(resistor.n, inductor.p)
        connect(inductor.n, isense.p)
        connect(isense.n, gyrator.n)
        connect(gyrator.p, ground.p)
        connect(source.n, ground.p)
        connect(shaft, tsense.b)
        connect(tsense.a, rotor.a)
        connect(rotor.a, gyrator.shaft)
        connect(rotor.a, damping.a)
        connect(rotor.a, wsense.a)
        connect(rotor.b, stator.a)
        connect(rotor.b, damping.b)
        connect(u, uin.u)
        connect(uin.y, source.u)
        connect(uin.y, pel.u1)
        connect(isense.y, pel.u2)
        connect(isense.y, i)
        connect(wsense.y, w)
        connect(tsense.y, tau)
        connect(tsense.y, pmech.u1)
        connect(wsense.y, pmech.u2)
        connect(pel.y, P_el)
        connect(pmech.y, P_mech)
    end
end
