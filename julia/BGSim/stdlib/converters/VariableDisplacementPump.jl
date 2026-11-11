@block VariableDisplacementPump begin
    # Variable-displacement pump: the FixedDisplacementPump with the displacement D*u set
    # by the signal input u (the displacement fraction, -1 to 1; negative reverses the
    # delivery, over-centre). With w = shaft.f and dp = b.e - a.e:
    #   Q = D*u*w - K_leak*dp
    #   T = D*u*dp + K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr)
    # The leakage K_leak = D*w_nom*(1 - eta_v)/p_nom and the friction K_fr =
    # D*(1 - eta_m)/eta_m are those of the full displacement, so both stay when u = 0 (a
    # pump at zero stroke still leaks and drags). The losses are never negative.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
        shaft::Power{Rotation}
    end
    @inputs u::Real
    @parameters begin
        D::Real = 1.6e-6, [unit = "m^3/rad", min = 0, description = "Maximum displacement per radian (u = 1)"]
        eta_v::Real = 0.95, [unit = "1", min = 1.0e-3, max = 1, description = "Volumetric efficiency at full displacement, nominal pressure and speed"]
        eta_m::Real = 0.9, [unit = "1", min = 1.0e-3, max = 1, description = "Hydromechanical efficiency at full displacement"]
        p_nom::Real = 1.0e7, [unit = "Pa", min = 1.0e-12, description = "Nominal pressure rise for eta_v"]
        w_nom::Real = 157.0, [unit = "rad/s", min = 1.0e-12, description = "Nominal shaft speed for eta_v"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 1.0e-12, description = "Pressure band that rounds |dp| in the friction torque"]
        w_tr::Real = 1.0, [unit = "rad/s", min = 1.0e-12, description = "Speed band over which the friction torque changes sign"]
    end
    @variables begin
        w::Real = 0.0, [unit = "rad/s", description = "Shaft speed"]
        dp::Real = 0.0, [unit = "Pa", description = "Pressure rise b minus a"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Delivered flow from a to b"]
        T::Real = 0.0, [unit = "N*m", description = "Shaft torque into the pump"]
        P_loss::Real = 0.0, [unit = "W", description = "Dissipated power (leakage plus friction)"]
    end
    @equations begin
        w ~ shaft.f
        dp ~ b.e - a.e
        Q ~ D * u * w - D * w_nom * (1.0 - eta_v) / p_nom * dp
        T ~ D * u * dp + D * (1.0 - eta_m) / eta_m * dp * tanh(dp / p_tr) * tanh(w / w_tr)
        P_loss ~ D * w_nom * (1.0 - eta_v) / p_nom * dp * dp +
                 D * (1.0 - eta_m) / eta_m * dp * tanh(dp / p_tr) * tanh(w / w_tr) * w
        a.f ~ Q
        b.f ~ -Q
        shaft.e ~ T
    end
    @orientation begin
        a => :in
        b => :in
        shaft => :in
    end
end
