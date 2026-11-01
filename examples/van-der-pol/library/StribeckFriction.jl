@block StribeckFriction begin
    # Friction contact between a belt and a block with the full Stribeck curve (Gaussian
    # Stribeck term plus viscous friction), a nonlinear R in resistance causality. The slip
    # w = p.f (belt minus block) sets the force on the block
    #   F(w) = F_n (mu_c + (mu_s - mu_c) exp(-(w/v_s)^2)) tanh(w/v_eps) + sigma w.
    # tanh(w/v_eps) is a smooth sign of the slip; it only matters if the block sticks, which this
    # example's oscillation never does (the slip stays well above v_eps).
    @ports p::Power{Generic}
    @parameters begin
        F_n::Real = 40.0, [min = 0, description = "Normal force (N)"]
        mu_c::Real = 0.3, [min = 0, description = "Coulomb (kinetic) friction coefficient"]
        mu_s::Real = 0.45, [min = 0, description = "Static friction coefficient"]
        v_s::Real = 0.1, [unit = "flow", min = 0, description = "Stribeck velocity (m/s)"]
        sigma::Real = 0.0, [min = 0, description = "Viscous friction coefficient (N*s/m)"]
        v_eps::Real = 1.0e-3, [unit = "flow", min = 0, description = "Slip velocity of the smooth sign tanh(w/v_eps) (m/s)"]
    end
    @outputs begin
        F::Real, [description = "Friction force on the block"]
        w::Real, [description = "Slip velocity, belt minus block"]
    end
    @equations begin
        p.e ~ F_n * (mu_c + (mu_s - mu_c) * exp(-(p.f / v_s)^2)) * tanh(p.f / v_eps) + sigma * p.f
        F ~ p.e
        w ~ p.f
    end
    @causality p => :effort_out
end
