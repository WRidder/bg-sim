@block WormGear begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        n::Real = 30.0, [unit = "1", min = 1.0e-12, description = "Gear ratio: worm speed over wheel speed (a.f = n * b.f)"]
        eta::Real = 0.7, [unit = "1", min = 1.0e-6, max = 1, description = "Efficiency when the worm a drives the wheel b"]
        eta_back::Real = 0.4, [unit = "1", max = 1, description = "Efficiency when the wheel b drives the worm a; 0 or less makes the gear self-locking"]
        w_eps::Real = 1.0e-3, [unit = "rad/s", min = 0, description = "Worm-speed smoothing of the friction direction: tanh(w/w_eps) when positive, the ifelse switch at zero"]
    end
    @variables begin
        s::Real = 0.0, [description = "Friction direction factor of the worm: the tanh smoothing or the ifelse switch"]
        T_loss::Real = 0.0, [unit = "N*m", description = "Mesh friction torque at the worm, always against the worm speed"]
    end
    @equations begin
        a.f ~ n * b.f
        # An ideal gear plus a load-dependent mesh friction at the worm. Its size makes the
        # power out eta times the power in while the worm drives (b.e * s < 0) and eta_back
        # times the power in while the wheel drives; with eta_back <= 0 the friction is
        # larger than what the wheel can push, so the gear locks. The two branches meet at
        # b.e = 0, so the law is continuous, and the friction direction follows the worm
        # speed as in RotationalFriction. The lost heat T_loss*a.f would go to a later
        # thermal port.
        s ~ ifelse(w_eps > 0.0, tanh(a.f / w_eps), ifelse(a.f > 0.0, 1.0, ifelse(a.f < 0.0, -1.0, 0.0)))
        T_loss ~ abs(b.e) / n * s * ifelse(b.e * s < 0.0, 1.0 / eta - 1.0, 1.0 - eta_back)
        a.e ~ -b.e / n + T_loss
    end
    @causality (a, b) => :transformer
    @orientation begin
        a => :in
        b => :in
    end
end
