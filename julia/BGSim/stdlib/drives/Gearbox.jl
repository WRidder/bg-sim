@block Gearbox begin
    # Ideal, efficiency-free gearbox (J-MB11) on the documented `IdealGear` primitive: the
    # motor side `a` turns `N` times as fast as the output side `b` (`a.f = N b.f`,
    # `b.e = -N a.e`, so `a.e a.f + b.e b.f = 0`). A rotor inertia `J_m` on the motor side
    # therefore appears at the output as the reflected inertia `N^2 J_m`.
    #
    # Taps: `w_a` and `w_b` (rad/s), `tau_b` (N*m, the torque delivered through the output
    # side) and `P` (W, `tau_b * w_b`, equal to the power taken at the motor side).
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @outputs begin
        w_a::Real, [unit = "rad/s"]
        w_b::Real, [unit = "rad/s"]
        tau_b::Real, [unit = "N*m"]
        P::Real, [unit = "W"]
    end
    @parameters N::Real = 10.0, [min = 0, description = "Ratio (motor rate = N * output rate)"]
    @components begin
        gear = IdealGear(n = N)
        sense_a = SpeedSensor()
        sense_b = SpeedSensor()
        torque_b = TorqueSensor()
        power = Product()
    end
    @connections begin
        connect(a, gear.a)
        connect(sense_a.a, gear.a)
        connect(gear.b, torque_b.a)
        connect(b, torque_b.b)
        connect(sense_b.a, torque_b.b)
        connect(sense_a.y, w_a)
        connect(sense_b.y, w_b)
        connect(torque_b.y, tau_b)
        connect(torque_b.y, power.u1)
        connect(sense_b.y, power.u2)
        connect(power.y, P)
    end
end
