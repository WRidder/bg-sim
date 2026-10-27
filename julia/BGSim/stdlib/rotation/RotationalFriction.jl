@block RotationalFriction begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        Fs::Real = 5.0, [unit = "N*m", min = 0, description = "Static friction torque: the Stribeck magnitude at zero speed"]
        Fc::Real = 3.0, [unit = "N*m", min = 0, description = "Coulomb friction torque: the Stribeck magnitude at high speed"]
        Fv::Real = 10.0, [unit = "N*m*s/rad", min = 0, description = "Viscous friction coefficient"]
        v_s::Real = 0.01, [unit = "rad/s", min = 1.0e-12, description = "Stribeck speed: the decay rate of the static-to-Coulomb transition"]
        v_eps::Real = 1.0e-3, [unit = "rad/s", min = 0, description = "Speed smoothing: tanh(w/v_eps) when positive, the ifelse switch at zero"]
    end
    @variables s::Real = 0.0, [description = "Friction direction factor: the tanh smoothing or the ifelse switch"]
    @equations begin
        # The rotational twin of the translational Friction block: `v_eps > 0` selects the
        # smooth branch, otherwise the exact switch is an `ifelse` on the relative speed.
        s ~ ifelse(
            v_eps > 0.0,
            tanh((a.f - b.f) / v_eps),
            ifelse(a.f - b.f > 0.0, 1.0, ifelse(a.f - b.f < 0.0, -1.0, 0.0)),
        )
        a.e ~ (Fc + (Fs - Fc) * exp(-abs(a.f - b.f) / v_s)) * s + Fv * (a.f - b.f)
        b.e ~ -a.e
    end
end
