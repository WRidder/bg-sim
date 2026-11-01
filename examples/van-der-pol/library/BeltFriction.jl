@block BeltFriction begin
    # Friction contact between a belt and a block, as a nonlinear R in resistance causality:
    # the slip velocity w = p.f (belt minus block) sets the friction force F = p.e on the block.
    # The friction-velocity curve is its third-order Taylor fit about the belt speed v_b, an
    # inflection point of the curve, so it has no quadratic term:
    #   F(w) = F0 - alpha (w - v_b) + beta (w - v_b)^3.
    # alpha > 0 is the falling slope (the Stribeck effect net of the viscous rise), beta > 0 the
    # curvature that limits it. With w = v_b - x' this is the negative damper of Rayleigh's
    # equation.
    @ports p::Power{Generic}
    @parameters begin
        F0::Real = 13.4, [unit = "effort", description = "Friction force at the belt speed (N)"]
        alpha::Real = 5.0, [min = 0, description = "Falling slope -dF/dw at v_b (N*s/m)"]
        beta::Real = 1.0e3, [min = 0, description = "Cubic coefficient F'''(v_b)/6 (N*s^3/m^3)"]
        v_b::Real = 0.0707, [unit = "flow", description = "Belt speed, the expansion point (m/s)"]
    end
    @outputs begin
        F::Real, [description = "Friction force on the block"]
        w::Real, [description = "Slip velocity, belt minus block"]
        dF::Real, [description = "Deviation from the force at the belt speed, F - F0"]
    end
    @equations begin
        dF ~ -alpha * (p.f - v_b) + beta * (p.f - v_b)^3
        p.e ~ F0 + dF
        F ~ p.e
        w ~ p.f
    end
    @causality p => :effort_out
end
