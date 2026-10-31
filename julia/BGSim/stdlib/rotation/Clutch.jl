@block Clutch begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @inputs f_n::Real, [unit = "N", description = "Normal force that presses the plates together; values below zero count as an open clutch"]
    @parameters begin
        mu_s::Real = 0.5, [unit = "1", min = 0, description = "Static friction coefficient: the Stribeck value at zero slip"]
        mu_c::Real = 0.4, [unit = "1", min = 0, description = "Kinetic (Coulomb) friction coefficient at high slip"]
        r_eff::Real = 0.05, [unit = "m", min = 0, description = "Effective friction radius of the plates"]
        n_faces::Real = 2.0, [unit = "1", min = 0, description = "Number of friction faces"]
        w_s::Real = 0.01, [unit = "rad/s", min = 1.0e-12, description = "Stribeck speed: the decay rate of the static-to-kinetic transition"]
        w_eps::Real = 1.0e-3, [unit = "rad/s", min = 0, description = "Slip-speed smoothing: tanh(w/w_eps) when positive, the ifelse switch at zero"]
    end
    @variables begin
        w::Real = 0.0, [unit = "rad/s", description = "Slip speed a minus b"]
        s::Real = 0.0, [description = "Friction direction factor: the tanh smoothing or the ifelse switch"]
        T::Real = 0.0, [unit = "N*m", description = "Friction torque carried from a to b"]
    end
    @equations begin
        w ~ a.f - b.f
        # Stick-slip as in RotationalFriction: `w_eps > 0` selects the smooth tanh branch,
        # otherwise the exact switch is an `ifelse` on the slip speed.
        s ~ ifelse(w_eps > 0.0, tanh(w / w_eps), ifelse(w > 0.0, 1.0, ifelse(w < 0.0, -1.0, 0.0)))
        # Disc friction: normal force times the friction coefficient, the effective radius
        # and the number of faces. A pulling (negative) force opens the clutch. The heat
        # T*w is lost here; a later thermal port would carry it.
        T ~ n_faces * r_eff * max(f_n, 0.0) * (mu_c + (mu_s - mu_c) * exp(-abs(w) / w_s)) * s
        a.e ~ T
        b.e ~ -T
    end
end
