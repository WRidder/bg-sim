@block Brake begin
    @ports a::Power{Rotation}
    @inputs f_n::Real, [unit = "N", description = "Normal force on the brake pads; values below zero count as a released brake"]
    @parameters begin
        mu_s::Real = 0.5, [unit = "1", min = 0, description = "Static friction coefficient: the Stribeck value at zero speed"]
        mu_c::Real = 0.4, [unit = "1", min = 0, description = "Kinetic (Coulomb) friction coefficient at high speed"]
        r_eff::Real = 0.05, [unit = "m", min = 0, description = "Effective friction radius of the pads"]
        n_faces::Real = 2.0, [unit = "1", min = 0, description = "Number of friction faces"]
        w_s::Real = 0.01, [unit = "rad/s", min = 1.0e-12, description = "Stribeck speed: the decay rate of the static-to-kinetic transition"]
        w_eps::Real = 1.0e-3, [unit = "rad/s", min = 0, description = "Speed smoothing: tanh(w/w_eps) when positive, the ifelse switch at zero"]
    end
    @variables begin
        s::Real = 0.0, [description = "Friction direction factor: the tanh smoothing or the ifelse switch"]
        T::Real = 0.0, [unit = "N*m", description = "Braking torque taken from a"]
    end
    @equations begin
        # The Clutch with its second flange fixed to the housing (ground). The heat T*a.f is
        # lost here; a later thermal port would carry it.
        s ~ ifelse(w_eps > 0.0, tanh(a.f / w_eps), ifelse(a.f > 0.0, 1.0, ifelse(a.f < 0.0, -1.0, 0.0)))
        T ~ n_faces * r_eff * max(f_n, 0.0) * (mu_c + (mu_s - mu_c) * exp(-abs(a.f) / w_s)) * s
        a.e ~ T
    end
    @orientation a => :in
end
