@block Crank begin
    # Crank-rocker flapping mechanism of both wings from one crank shaft (a power-conserving modulated
    # transformer with three rotation ports). The crank angle psi is the integral of the crank speed
    # `a.f`; the wing flap angle follows the kinematic map of the linkage
    #
    #   phi(psi) = Phi [ sin(psi) + h2 sin(2 psi + ph2) ] ,   dphi/dpsi = Phi [ cos(psi) + 2 h2 cos(2 psi + ph2) ]
    #
    # (a sinusoidal stroke with a second harmonic for the asymmetric up/down stroke of a four-bar), so
    #
    #   bL.f = aL dphi/dpsi a.f ,    bR.f = aR dphi/dpsi a.f ,    a.e = - dphi/dpsi (aL bL.e + aR bR.e)
    #
    # and  a.e a.f + bL.e bL.f + bR.e bR.f = 0 exactly. `aL`, `aR` (nominally 1) scale the stroke
    # amplitude of each wing (the eccentric of the crank pin): the asymmetric flapping amplitude
    # used for roll. The second (rear) rod of the thesis' actuator is the pitch rest angle Theta sin(psi + ps) of the
    # torsion springs of the wing roots (`pitL`, `pitR`, mirrored in sign because the left and right joint x axes are
    # opposite); it is a kinematic input like the thesis' velocity-controlled rods. Reaction torques of the wings come back on the shaft through `a.e`.
    @ports begin
        a::Power{Rotation}
        bL::Power{Rotation}
        bR::Power{Rotation}
    end
    @inputs begin
        aL::Real
        aR::Real
    end
    @outputs begin
        pitL::Real, [unit = "rad"]
        pitR::Real, [unit = "rad"]
        psi_out::Real, [unit = "rad"]
        phi_kin::Real, [unit = "rad"]
        dphi_out::Real
    end
    @parameters begin
        Phi::Real = 0.5, [unit = "rad", min = 0, description = "Flap amplitude of the first harmonic"]
        h2::Real = 0.06, [min = 0, description = "Second harmonic ratio"]
        ph2::Real = 0.8, [unit = "rad", description = "Second harmonic phase"]
        Theta::Real = 0.2, [unit = "rad", min = 0, description = "Pitch amplitude of the rear rod"]
        ps::Real = 0.0, [unit = "rad", description = "Phase of the rear rod relative to the crank"]
        inc::Real = 0.0, [unit = "rad", description = "Rigging incidence of the wing roots (nose-up)"]
        psi0::Real = 0.0, [unit = "rad", description = "Initial crank angle"]
    end
    @variables begin
        psi::Real = 0.0, [unit = "rad", state = :prefer, description = "Crank angle"]
        dphi::Real = 0.0, [description = "Transmission ratio dphi/dpsi"]
    end
    @equations begin
        ddt(psi) ~ a.f
        dphi ~ Phi * (cos(psi + psi0) + 2.0 * h2 * cos(2.0 * (psi + psi0) + ph2))
        bL.f ~ aL * dphi * a.f
        bR.f ~ aR * dphi * a.f
        a.e ~ -dphi * (aL * bL.e + aR * bR.e)
        pitL ~ Theta * sin(psi + psi0 + ps) - inc
        pitR ~ -Theta * sin(psi + psi0 + ps) + inc
        psi_out ~ psi + psi0
        phi_kin ~ Phi * (sin(psi + psi0) + h2 * sin(2.0 * (psi + psi0) + ph2))
        dphi_out ~ dphi
    end
    @orientation begin
        a => :in
        bL => :in
        bR => :in
    end
end
