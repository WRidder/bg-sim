@block Electromagnet begin
    # Variable-reluctance actuator (lifting magnet, maglev coil): a two-port IC-field between
    # the coil (electrical p, n) and the gap (translation stator a, armature b). Its stored
    # magnetic energy, as a function of the flux linkage lambda and the gap h, is
    #   W(lambda, h) = lambda^2 / (2*L(h)),   L(h) = L_inf + 2*alpha/(h + h0),
    # with the co-energy W'(i, h) = L(h)*i^2/2. The port laws are its partial derivatives:
    #   i = dW/dlambda = lambda/L(h)                       (electrical port, I-type)
    #   F = dW/dh      = -dW'/dh = alpha*i^2/(h + h0)^2   (mechanical port, C-type)
    # F is the attraction that pulls the armature toward the magnet face; b.e = F, a.e = -F,
    # so the power into the block, (p.e - n.e)*i + F*(b.f - a.f), is exactly dW/dt: the
    # field stores energy and dissipates none (the coil resistance is a separate R).
    # The gap grows when the armature moves away from the stator: dh/dt = b.f - a.f.
    # States are the current i and the gap h; dlambda/dt = v is written for i through
    # dlambda/dt = L(h)*di/dt + dL/dh*dh/dt*i. h0 = 0 is the inverse-square law
    # F = alpha*i^2/h^2 of the MathWorks maglev model; h0 > 0 keeps L and F finite at contact.
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters begin
        alpha::Real = 2.4832e-5, [unit = "H*m", min = 0, description = "Force constant: F = alpha*i^2/(h + h0)^2 (N*m^2/A^2 = H*m); L(h) = L_inf + 2*alpha/(h + h0)"]
        L_inf::Real = 0.03, [unit = "H", min = 1.0e-12, description = "Coil inductance at an infinite gap (leakage and iron path)"]
        h0::Real = 0.0, [unit = "m", min = 0, description = "Gap offset: the magnetic gap at h = 0 (0 is the pure inverse-square law)"]
    end
    @variables begin
        i::Real = 0.0, [unit = "A", state = :prefer, description = "Coil current, from p through the coil to n"]
        h::Real = 0.1, [unit = "m", state = :prefer, description = "Gap from the magnet face to the armature (keep it above -h0)"]
        v::Real = 0.0, [unit = "V", description = "Coil voltage p minus n"]
        L::Real = 0.0, [unit = "H", description = "Gap-dependent inductance L(h)"]
        lambda::Real = 0.0, [unit = "V*s", description = "Flux linkage L(h)*i"]
        F::Real = 0.0, [unit = "N", description = "Attraction on the armature, toward the magnet face"]
        W::Real = 0.0, [unit = "J", description = "Stored magnetic energy L(h)*i^2/2"]
        P_el::Real = 0.0, [unit = "W", description = "Electrical power into the coil terminals"]
        P_mech::Real = 0.0, [unit = "W", description = "Mechanical power into the gap port, F*dh/dt (negative while the magnet does work on the armature)"]
    end
    @equations begin
        v ~ p.e - n.e
        p.f ~ i
        n.f ~ -i
        L ~ L_inf + 2.0 * alpha / (h + h0)
        lambda ~ L * i
        ddt(h) ~ b.f - a.f
        ddt(i) ~ (v + 2.0 * alpha * i * (b.f - a.f) / ((h + h0) * (h + h0))) / L
        F ~ alpha * i * i / ((h + h0) * (h + h0))
        b.e ~ F
        a.e ~ -F
        W ~ 0.5 * L * i * i
        P_el ~ v * i
        P_mech ~ F * (b.f - a.f)
    end
    # Integral causality of the IC-field: the state i sets the flow at the coil, the states
    # (i, h) set the force at the gap. Only bonded ports take part in SCAP.
    @causality begin
        p => :flow_out
        n => :flow_out
        a => :effort_out
        b => :effort_out
    end
end
