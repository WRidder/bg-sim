@block ALGearSpring begin
    # Torsional compliance of the planetary gear with backlash, as one bond-graph element on the
    # 0-junction between the rotor (referred to the output) and the arm: a nonlinear C (state:
    # the deflection phi, flow in = rotor rate / N minus arm rate) with contact damping in parallel.
    #
    #   smooth dead zone  D(phi) = s(phi - b) - s(-phi - b),  s(x) = (x + sqrt(x^2 + eps^2))/2,
    #                     b = backlash/2, eps = eps_frac * b
    #   hardening spring  T = k3 D - (k3 - k1) Dk tanh(D/Dk),  Dk = tau_knee/k1
    #                     (stiffness k1 at small load, k3 above the knee torque)
    #   contact damping   d w D'(phi),  D' in [0, 1] the slope of the dead zone (0 in the gap)
    #
    # D is smooth everywhere (no max/abs kink, no event) and odd; inside the gap the stiffness is
    # about k1 eps^2/(2 b^2), so the rotor floats almost free. E is the stored spring energy, the
    # integral of T dphi (T depends on phi alone, so it is a potential); P is the damping loss.
    @ports p::Power{Rotation}
    @outputs begin
        tau::Real, [unit = "N*m", description = "Gear torque (spring + damping)"]
        defl::Real, [unit = "rad", description = "Deflection, rotor/N minus arm"]
        E::Real, [unit = "J", description = "Stored spring energy"]
        P::Real, [unit = "W", description = "Contact damping loss"]
    end
    @parameters begin
        k1::Real = 1500.0, [unit = "N*m/rad", min = 0, description = "Stiffness below the knee"]
        k3::Real = 4000.0, [unit = "N*m/rad", min = 0, description = "Stiffness above the knee"]
        tau_knee::Real = 1.5, [unit = "N*m", min = 1e-9, description = "Knee torque"]
        backlash::Real = 0.0064, [unit = "rad", min = 0, description = "Total lost motion (both directions)"]
        eps_frac::Real = 0.2, [min = 1e-6, description = "Smoothing of the gap edges, fraction of backlash/2"]
        d::Real = 0.4, [unit = "N*m*s/rad", min = 0, description = "Contact damping"]
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Deflection"]
        Es::Real = 0.0, [unit = "J", state = :prefer, description = "Spring energy"]
        dz::Real = 0.0, [unit = "rad", description = "Dead-zone deflection D(phi)"]
        slope::Real = 0.0, [description = "D'(phi)"]
        ts::Real = 0.0, [unit = "N*m", description = "Spring torque"]
    end
    @equations begin
        ddt(phi) ~ p.f
        dz ~ 0.5 * (phi - 0.5 * backlash + sqrt((phi - 0.5 * backlash)^2 + (eps_frac * 0.5 * backlash + 1e-9)^2)) -
             0.5 * (-phi - 0.5 * backlash + sqrt((-phi - 0.5 * backlash)^2 + (eps_frac * 0.5 * backlash + 1e-9)^2))
        slope ~ 0.5 * (1 + (phi - 0.5 * backlash) / sqrt((phi - 0.5 * backlash)^2 + (eps_frac * 0.5 * backlash + 1e-9)^2)) +
                0.5 * (1 + (-phi - 0.5 * backlash) / sqrt((-phi - 0.5 * backlash)^2 + (eps_frac * 0.5 * backlash + 1e-9)^2))
        ts ~ k3 * dz - (k3 - k1) * (tau_knee / k1) * tanh(dz * k1 / tau_knee)
        p.e ~ ts + d * slope * p.f
        ddt(Es) ~ ts * p.f
        tau ~ p.e
        defl ~ phi
        E ~ Es
        P ~ d * slope * p.f * p.f
    end
    @orientation p => :in
end
