@block DCMotorThermal begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        shaft::Power{Rotation}
        housing::Power{Rotation}
        winding::Power{Thermal}
    end
    # The DC motor with its copper loss on a heat port: the winding resistance is a
    # `ResistorHeated`, so R follows the winding temperature and every joule of i^2*R leaves
    # through `winding` as heat flow. Connect a `HeatCapacitor` (the winding mass) to it.
    @parameters begin
        R::Real = 2.0, [unit = "Ohm", min = 0, description = "Winding resistance at the reference temperature T_ref"]
        alpha::Real = 0.00393, [unit = "1/K", description = "Temperature coefficient of the winding resistance (copper)"]
        T_ref::Real = 293.15, [unit = "K", min = 0, description = "Reference temperature of R"]
        L::Real = 5e-4, [unit = "H", min = 0, description = "Winding inductance"]
        k_t::Real = 0.05, [unit = "N*m/A", description = "Torque constant"]
        J::Real = 1e-5, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        d::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Internal viscous damping (its loss is not routed to the heat port)"]
    end
    @components begin
        resistor = ResistorHeated(R0 = R, alpha = alpha, T0 = T_ref)
        inductor = Inductor(L = L)
        # Wired exactly as in `DCMotor`: through `gyrator.p` and `gyrator.n` in reverse, so the
        # motor torque at the shaft is -k_t*i and the back-EMF +k_t*w_rel.
        gyrator = EMConverter(k = k_t)
        rotor = Inertia(J = J)
        damping = RotationalDamper(d = d)
    end
    @connections begin
        connect(p, resistor.p)
        connect(resistor.n, inductor.p)
        connect(inductor.n, gyrator.n)
        connect(gyrator.p, n)
        connect(winding, resistor.heat)
        connect(shaft, rotor.a)
        connect(rotor.a, gyrator.shaft)
        connect(rotor.a, damping.a)
        connect(rotor.b, housing)
        connect(rotor.b, damping.b)
    end
    @observables begin
        i = inductor.i
        w_rel = rotor.w
        R_hot = resistor.R
        P_loss = resistor.P
        p.e = resistor.p.e
        p.f = resistor.p.f
        n.e = gyrator.p.e
        n.f = gyrator.p.f
        shaft.e = rotor.a.e
        shaft.f = rotor.a.f
        housing.e = rotor.b.e
        housing.f = rotor.b.f
        winding.e = resistor.heat.e
        winding.f = resistor.heat.f
    end
end
