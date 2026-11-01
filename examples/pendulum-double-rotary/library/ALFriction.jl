@block ALFriction begin
    # Smooth Coulomb + Stribeck + viscous friction as a bond-graph R element (one port, flow in,
    # effort out). For the flow w (rad/s):
    #
    #   tau = (Fc + (Fs - Fc) exp(-(w/vs)^2)) tanh(w/v_eps) + Fv w
    #
    # Every term is smooth: tanh instead of sign, the Gaussian Stribeck term instead of
    # exp(-|w|/vs), so there is no max/abs/ifelse kink and no zero-crossing event (a tangent-zero
    # kink makes the root finder chatter, see examples/van-der-pol/library/EnergySplit.jl).
    # v_eps is far below the speeds of interest; the friction power tau w >= 0 always.
    @ports p::Power{Rotation}
    @outputs begin
        tau::Real, [unit = "N*m", description = "Friction torque"]
        P::Real, [unit = "W", description = "Dissipated power"]
    end
    @parameters begin
        Fc::Real = 0.1, [unit = "N*m", min = 0, description = "Coulomb friction"]
        Fs::Real = 0.15, [unit = "N*m", min = 0, description = "Breakaway (static) friction"]
        vs::Real = 0.5, [unit = "rad/s", min = 1e-9, description = "Stribeck speed"]
        Fv::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Viscous friction"]
        v_eps::Real = 0.002, [unit = "rad/s", min = 1e-12, description = "Smoothing speed of the Coulomb term"]
    end
    @equations begin
        tau ~ (Fc + (Fs - Fc) * exp(-(p.f / vs) * (p.f / vs))) * tanh(p.f / v_eps) + Fv * p.f
        p.e ~ tau
        P ~ tau * p.f
    end
end
