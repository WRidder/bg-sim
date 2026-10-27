@block DCMotor begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        shaft::Power{Rotation}
        housing::Power{Rotation}
    end
    # J2.6b: a composite's parameters are exposed at the composite's own path (`Motor1/R`)
    # and aliased into the components below, so they stay runtime-tunable (decision D4).
    @parameters begin
        R::Real = 2.0, [unit = "Ohm", min = 0, description = "Winding resistance"]
        L::Real = 5e-4, [unit = "H", min = 0, description = "Winding inductance"]
        k_t::Real = 0.05, [unit = "N*m/A", description = "Torque constant"]
        J::Real = 1e-5, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        d::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Internal viscous damping"]
    end
    @components begin
        resistor = Resistor(R = R)
        inductor = Inductor(L = L)
        # The electrical side is wired through `gyrator.p` and `gyrator.n` in reverse: with
        # the gyrator's `shaft.e = +k*p.f`, that makes the motor torque at the shaft -k_t*i
        # and the back-EMF +k_t*w_rel, the orientation CONTRACT-5 measured for the flat block.
        gyrator = EMConverter(k = k_t)
        rotor = Inertia(J = J)
        damping = RotationalDamper(d = d)
    end
    @connections begin
        connect(p, resistor.p)
        connect(resistor.n, inductor.p)
        connect(inductor.n, gyrator.n)
        connect(gyrator.p, n)
        # The rotor Inertia and the internal damper sit across shaft-housing; the shaft face
        # is exposed through the rotor, so the external load joins the same rotational node.
        connect(shaft, rotor.a)
        connect(rotor.a, gyrator.shaft)
        connect(rotor.a, damping.a)
        connect(rotor.b, housing)
        connect(rotor.b, damping.b)
    end
    # The flat block's recorded signals keep their names at the composite path.
    @observables begin
        i = inductor.i
        w_rel = rotor.w
        p.e = resistor.p.e
        p.f = resistor.p.f
        n.e = gyrator.p.e
        n.f = gyrator.p.f
        shaft.e = rotor.a.e
        shaft.f = rotor.a.f
        housing.e = rotor.b.e
        housing.f = rotor.b.f
    end
end
