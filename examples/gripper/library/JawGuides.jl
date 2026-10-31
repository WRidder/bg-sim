@block JawGuides begin
    # Friction of the jaw guides (both jaws, in the jaw-closing coordinate): Stribeck friction
    # with a Gaussian decay and a tanh direction, plus viscous friction. Smooth everywhere (no
    # abs, so no kink events while the jaws stand still):
    #
    #   F = (Fc + (Fs - Fc) exp(-(v/v_s)^2)) tanh(v/v_eps) + Fv v,   v = a.f - b.f
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        Fs::Real = 4.0, [unit = "N", min = 0, description = "Static (breakaway) friction force"]
        Fc::Real = 3.0, [unit = "N", min = 0, description = "Coulomb friction force"]
        Fv::Real = 10.0, [unit = "N*s/m", min = 0, description = "Viscous friction coefficient"]
        v_s::Real = 0.005, [unit = "m/s", min = 1.0e-12, description = "Stribeck velocity"]
        v_eps::Real = 1.0e-4, [unit = "m/s", min = 1.0e-12, description = "Velocity smoothing of the friction direction"]
    end
    @variables v::Real = 0.0, [unit = "m/s", description = "Sliding speed"]
    @equations begin
        v ~ a.f - b.f
        a.e ~ (Fc + (Fs - Fc) * exp(-(v / v_s)^2)) * tanh(v / v_eps) + Fv * v
        b.e ~ -a.e
    end
end
