@block GazFriction begin
    # Joint friction of the Franka Emika Panda as a nonlinear bond-graph R element (D28): the
    # constitutive law only, effort from flow, no state. Gaz et al. 2019 (supplementary Table I):
    #
    #   tau_f(qd) = phi1 / (1 + exp(-phi2 (qd + phi3))) - phi1 / (1 + exp(-phi2 phi3))
    #
    # A smooth (sigmoid) Coulomb-like friction with an offset `phi3`, zero at rest (the second
    # term), saturating at `phi1 / (1 + exp(phi2 phi3))`-ish for fast motion; its slope at rest
    # acts as a viscous coefficient of about phi1 phi2 / 4. Smooth, so it creates no events. The
    # stdlib `R` is linear and `MR` would need the secant tau_f/qd (singular at rest), hence a
    # project element.
    @ports p::Power{Rotation}
    @parameters begin
        phi1::Real = 0.5, [unit = "N*m", min = 0, description = "Friction level (Gaz phi1)"]
        phi2::Real = 5.0, [unit = "s/rad", min = 0, description = "Sigmoid steepness (Gaz phi2)"]
        phi3::Real = 0.0, [unit = "rad/s", description = "Sigmoid offset (Gaz phi3)"]
    end
    @equations begin
        p.e ~ phi1 / (1.0 + exp(-phi2 * (p.f + phi3))) - phi1 / (1.0 + exp(-phi2 * phi3))
    end
end
