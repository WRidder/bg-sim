@block Friction begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        Fs::Real = 5.0, [unit = "N", min = 0, description = "Static friction force: the Stribeck magnitude at zero velocity"]
        Fc::Real = 3.0, [unit = "N", min = 0, description = "Coulomb friction force: the Stribeck magnitude at high velocity"]
        Fv::Real = 10.0, [unit = "N*s/m", min = 0, description = "Viscous friction coefficient"]
        v_s::Real = 0.01, [unit = "m/s", min = 1.0e-12, description = "Stribeck velocity: the decay rate of the static-to-Coulomb transition"]
        v_eps::Real = 1.0e-3, [unit = "m/s", min = 0, description = "Velocity smoothing: tanh(v/v_eps) when positive, the ifelse switch at zero"]
    end
    @variables s::Real = 0.0, [description = "Friction direction factor: the tanh smoothing or the ifelse switch"]
    @equations begin
        # `v_eps > 0` selects the smooth branch; otherwise the exact switch is an `ifelse`
        # on the relative velocity, the non-smooth form the event collector sees (plan 5.8).
        s ~ ifelse(
            v_eps > 0.0,
            tanh((a.f - b.f) / v_eps),
            ifelse(a.f - b.f > 0.0, 1.0, ifelse(a.f - b.f < 0.0, -1.0, 0.0)),
        )
        a.e ~ (Fc + (Fs - Fc) * exp(-abs(a.f - b.f) / v_s)) * s + Fv * (a.f - b.f)
        b.e ~ -a.e
    end
end
