@block CupValve begin
    # The vacuum line between the manifold (`a`) and one cup (`b`): a regularised orifice whose
    # area can carry two industrial options, so one block covers the three supply variants.
    #
    #   dP = b.e - a.e                              cup minus manifold pressure (> 0 when evacuating)
    #   Q  = Cd A dP sqrt(2 / (rho sqrt(dP^2 + p_tr^2)))   free-air flow from the cup to the manifold
    #   A  = A_line (r_rev + (1 - r_rev) sigma(dP / p_tr))                     check valve
    #               (1 - (1 - bleed) sigma((dP - dp_close) / dp_w))           flow-closing valve
    #   sigma(z) = (1 + tanh(z)) / 2
    #
    # Plain line: `r_rev = 1`, `dp_close` very large. Check (non-return) valve: `r_rev` small, so
    # a cup keeps its vacuum when the manifold pressure rises. Flow restrictor valve ("SCR"
    # ball valve): above the closing pressure drop `dp_close` (a cup sucking open air) the area
    # falls to the bleed `bleed * A_line`, so one open or lost cup cannot pull the manifold
    # down; once the cup is sealed again the bleed evacuates it and the valve reopens. A fixed
    # restrictor nozzle is just a small `A_line`.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @parameters begin
        A_line::Real = 7.0e-6, [unit = "m^2", min = 0, description = "Open flow area of the line"]
        Cd::Real = 0.6, [unit = "1", min = 0, description = "Discharge coefficient"]
        rho::Real = 1.2, [unit = "kg/m^3", min = 1.0e-12, description = "Air density (free air)"]
        p_tr::Real = 200.0, [unit = "Pa", min = 1.0e-6, description = "Transition pressure of the regularised law"]
        r_rev::Real = 1.0, [unit = "1", min = 0, max = 1, description = "Reverse-flow area fraction (1 = no check valve)"]
        dp_close::Real = 1.0e9, [unit = "Pa", description = "Pressure drop at which the flow valve closes (very large = no flow valve)"]
        dp_w::Real = 1000.0, [unit = "Pa", min = 1.0e-6, description = "Width of the closing transition"]
        bleed::Real = 0.02, [unit = "1", min = 0, max = 1, description = "Bleed area fraction of a closed flow valve"]
    end
    @variables begin
        dP::Real = 0.0, [unit = "Pa", description = "Cup minus manifold pressure"]
        A::Real = 7.0e-6, [unit = "m^2", description = "Effective flow area"]
    end
    @outputs Q::Real, [unit = "m^3/s", description = "Free-air flow from the cup to the manifold"]
    @equations begin
        dP ~ b.e - a.e
        A ~ A_line * (r_rev + (1 - r_rev) * 0.5 * (1 + tanh(dP / p_tr))) *
            (1 - (1 - bleed) * 0.5 * (1 + tanh((dP - dp_close) / dp_w)))
        Q ~ Cd * A * dP * sqrt(2 / (rho * sqrt(dP * dP + p_tr * p_tr)))
        b.f ~ Q
        a.f ~ -Q
    end
    @orientation begin
        a => :in
        b => :in
    end
end
