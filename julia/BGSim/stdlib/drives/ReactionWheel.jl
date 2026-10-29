@block ReactionWheel begin
    # Reaction wheel (J-MB11): a voltage-driven DC motor between a free `housing` and a wheel
    # of absolute inertia `J_w`, with the **reaction on the housing**. The housing port is a
    # `Rotation` port whose flow is the housing's absolute angular rate, so it bonds to a joint
    # drive axis (`Revolute2D*`, `drive`: `qdot`) of the body that carries the wheel, and the
    # effort the housing port delivers is the torque on that body.
    #
    # STATUS NOTE-8: `EMConverter` is a three-port block (`p`, `n`, `shaft`), referenced to an
    # inertial shaft frame, so it has no stator reaction. Here the electromechanical coupling
    # is written as the pair of signal-coupled element sets that a four-port converter means:
    #
    #   torque pair   TorqueSource(T = k_t), housing side `a`, wheel side `b`, driven by the
    #                 winding current: `+k_t i` on the wheel and `-k_t i` on the housing
    #   back-EMF      two series VoltageSource elements (the second reversed), `k_t w_w` and `-k_t w_h`, so the
    #                 winding sees `k_t (w_w - w_h)`, the rate of the rotor **relative to the
    #                 stator**, whatever the housing does
    #
    # The two halves exchange exactly `k_t i (w_w - w_h)`, so `tau` and `-tau` are an
    # action/reaction pair and the total angular momentum of housing body plus wheel is
    # conserved when nothing else acts. The wheel inertia `J_w` is absolute (referenced to
    # the inertial frame), the rotor inertia is part of it; `b_m` is a viscous loss on the
    # relative rate.
    #
    # Taps: `i` (A), `w_w` (rad/s, absolute wheel rate), `tau` (N*m, motor torque on the wheel,
    # `k_t i`), `H_w` (N*m*s, wheel angular momentum `J_w w_w`) and `P_el` (W, `u i`); the
    # observed `phi_rel` (rad) is the wheel angle relative to the housing (`w_rel` is
    # `w_w - w_h`; the zero-stiffness `relative` shaft only senses the angle, it carries no torque).
    @ports housing::Power{Rotation}
    @inputs u::Real, [unit = "V"]
    @outputs begin
        i::Real, [unit = "A"]
        w_w::Real, [unit = "rad/s"]
        tau::Real, [unit = "N*m"]
        H_w::Real, [unit = "N*m*s"]
        P_el::Real, [unit = "W"]
    end
    @parameters begin
        R_w::Real = 2.0, [unit = "Ohm", min = 0, description = "Armature resistance"]
        L::Real = 5e-4, [unit = "H", min = 0, description = "Armature inductance"]
        k_t::Real = 0.05, [unit = "N*m/A", description = "Torque and back-EMF constant"]
        J_w::Real = 2e-3, [unit = "kg*m^2", min = 0, description = "Wheel inertia (absolute, rotor included)"]
        b_m::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Viscous loss on the relative rate"]
    end
    @components begin
        source = VoltageSource(V = 1.0)
        emf_wheel = VoltageSource(V = k_t)
        emf_housing = VoltageSource(V = k_t)
        ground = Ground()
        resistor = Resistor(R = R_w)
        inductor = Inductor(L = L)
        isense = CurrentSensor()
        torque = TorqueSource(T = k_t)
        tgain = Gain(k = k_t)
        wheel = Inertia(J = J_w)
        inertial = FixedShaft()
        damping = RotationalDamper(d = b_m)
        relative = ElasticShaft(k = 0.0, d = 0.0)
        wsense = SpeedSensor()
        hsense = SpeedSensor()
        uin = Gain(k = 1.0)
        pel = Product()
        hgain = Gain(k = J_w)
    end
    @connections begin
        connect(source.p, resistor.p)
        connect(resistor.n, emf_wheel.p)
        connect(emf_wheel.n, emf_housing.n)
        connect(emf_housing.p, inductor.p)
        connect(inductor.n, isense.p)
        connect(isense.n, ground.p)
        connect(source.n, ground.p)
        connect(wheel.a, torque.b)
        connect(wheel.a, damping.a)
        connect(wheel.a, wsense.a)
        connect(wheel.b, inertial.a)
        connect(relative.a, wheel.a)
        connect(relative.b, torque.a)
        connect(torque.a, housing)
        connect(torque.a, damping.b)
        connect(torque.a, hsense.a)
        connect(u, uin.u)
        connect(uin.y, source.u)
        connect(uin.y, pel.u1)
        connect(wsense.y, emf_wheel.u)
        connect(hsense.y, emf_housing.u)
        connect(isense.y, torque.u)
        connect(isense.y, pel.u2)
        connect(isense.y, i)
        connect(isense.y, tgain.u)
        connect(tgain.y, tau)
        connect(wsense.y, w_w)
        connect(wsense.y, hgain.u)
        connect(hgain.y, H_w)
        connect(pel.y, P_el)
    end
    @observables begin
        phi_rel = relative.phi
    end
end
