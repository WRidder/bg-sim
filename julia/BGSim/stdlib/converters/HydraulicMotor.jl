@block HydraulicMotor begin
    # Fixed-displacement hydraulic motor from the hydraulic ports (inlet a, outlet b) to the
    # rotation shaft: the pump reversed. With w = shaft.f and the pressure drop
    # dp = a.e - b.e:
    #   Q = D*w + K_leak*dp                            (consumed flow, a -> b)
    #   T = D*dp - K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr)  (torque delivered to the load)
    # and the shaft port carries shaft.e = -T. K_leak = D*w_nom*(1 - eta_v)/(eta_v*p_nom)
    # gives the volumetric efficiency D*w/Q = eta_v at the nominal point, and
    # K_fr = D*(1 - eta_m) the delivered torque eta_m*D*dp there. The friction always
    # opposes the rotation, so the losses K_leak*dp^2 + T_fr*w are never negative.
    # eta_v = eta_m = 1 is the ideal motor, w = Q/D and T = D*dp.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
        shaft::Power{Rotation}
    end
    @parameters begin
        D::Real = 1.6e-6, [unit = "m^3/rad", min = 0, description = "Displacement per radian (cm^3/rev = D*2*pi*1e6)"]
        eta_v::Real = 0.95, [unit = "1", min = 1.0e-3, max = 1, description = "Volumetric efficiency at the nominal pressure and speed"]
        eta_m::Real = 0.9, [unit = "1", min = 0, max = 1, description = "Hydromechanical efficiency"]
        p_nom::Real = 1.0e7, [unit = "Pa", min = 1.0e-12, description = "Nominal pressure drop for eta_v"]
        w_nom::Real = 157.0, [unit = "rad/s", min = 1.0e-12, description = "Nominal shaft speed for eta_v"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 1.0e-12, description = "Pressure band that rounds |dp| in the friction torque"]
        w_tr::Real = 1.0, [unit = "rad/s", min = 1.0e-12, description = "Speed band over which the friction torque changes sign"]
    end
    @variables begin
        w::Real = 0.0, [unit = "rad/s", description = "Shaft speed"]
        dp::Real = 0.0, [unit = "Pa", description = "Pressure drop a minus b"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Consumed flow from a to b"]
        T::Real = 0.0, [unit = "N*m", description = "Torque delivered to the load"]
        P_loss::Real = 0.0, [unit = "W", description = "Dissipated power (leakage plus friction)"]
    end
    @equations begin
        w ~ shaft.f
        dp ~ a.e - b.e
        Q ~ D * w + D * w_nom * (1.0 - eta_v) / (eta_v * p_nom) * dp
        T ~ D * dp - D * (1.0 - eta_m) * dp * tanh(dp / p_tr) * tanh(w / w_tr)
        P_loss ~ D * w_nom * (1.0 - eta_v) / (eta_v * p_nom) * dp * dp +
                 D * (1.0 - eta_m) * dp * tanh(dp / p_tr) * tanh(w / w_tr) * w
        a.f ~ Q
        b.f ~ -Q
        shaft.e ~ -T
    end
    @orientation begin
        a => :in
        b => :in
        shaft => :in
    end
end
