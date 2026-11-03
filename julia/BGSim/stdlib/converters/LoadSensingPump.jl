@block LoadSensingPump begin
    # Variable-displacement pump with a load-sensing (LS) regulator, a pressure cut-off and a
    # torque (power) limiter: the VariableDisplacementPump whose displacement fraction x is
    # set by the pump's own regulator instead of a signal. Ports: suction a, delivery b, the
    # LS signal port ls (a pressure tap: it draws no flow, wire it to the LS line that the
    # shuttle valves feed with the highest load pressure) and the drive shaft.
    #
    # The regulator is static (the Simscape "pressure-compensated pump" form, applied to the
    # LS margin m = b.e - ls.e): the displacement is full while the margin is below the set
    # margin dp_ls and falls linearly to zero over the regulation range dp_reg, so in steady
    # state m sits between dp_ls and dp_ls + dp_reg and the pump delivers only the flow the
    # valves take. The cut-off does the same on the pressure rise dp = b.e - a.e at p_cut,
    # and the torque limiter caps the displacement at T_max/(D*dp), i.e. the power at
    # T_max*w at a constant shaft speed:
    #   x_ls = clamp((dp_ls + dp_reg - m)/dp_reg, 0, 1)
    #   x_pc = clamp((p_cut + dp_reg - dp)/dp_reg, 0, 1)
    #   x_tq = T_max/(D*sqrt(dp^2 + p_tr^2))
    #   x    = min(x_ls, x_pc, x_tq)
    # Every clamp and min is smooth (corners rounded over 1e-3 of the stroke), so there is
    # no switching event. With w = shaft.f, the flow and torque are the VariableDisplacement-
    # Pump's at the fraction x:
    #   Q = D*x*w - K_leak*dp
    #   T = D*x*dp + K_fr*dp*tanh(dp/p_tr)*tanh(w/w_tr)
    # with K_leak = D*w_nom*(1 - eta_v)/p_nom and K_fr = D*(1 - eta_m)/eta_m. The static
    # regulator has no lag of its own: with the pump-line volume it forms a first-order loop
    # (pole at beta*D*w/(V*dp_reg)), which is what keeps the LS loop well damped.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
        shaft::Power{Rotation}
        ls::Power{Hydraulic}
    end
    @parameters begin
        D::Real = 3.5e-5, [unit = "m^3/rad", min = 0, description = "Maximum displacement per radian (cm^3/rev = D*2*pi*1e6)"]
        eta_v::Real = 0.95, [unit = "1", min = 1.0e-3, max = 1, description = "Volumetric efficiency at full displacement, nominal pressure and speed"]
        eta_m::Real = 0.9, [unit = "1", min = 1.0e-3, max = 1, description = "Hydromechanical efficiency at full displacement"]
        p_nom::Real = 3.0e7, [unit = "Pa", min = 1.0e-12, description = "Nominal pressure rise for eta_v"]
        w_nom::Real = 188.5, [unit = "rad/s", min = 1.0e-12, description = "Nominal shaft speed for eta_v"]
        dp_ls::Real = 2.5e6, [unit = "Pa", min = 0, description = "LS margin: the pump holds b.e - ls.e at this pressure (plus up to dp_reg)"]
        dp_reg::Real = 2.0e5, [unit = "Pa", min = 1.0e-12, description = "Regulation range: full to zero displacement over this margin (or pressure) rise"]
        p_cut::Real = 3.2e7, [unit = "Pa", min = 0, description = "Pressure cut-off: the pump destrokes above this pressure rise"]
        T_max::Real = 1.0e9, [unit = "N*m", min = 1.0e-12, description = "Torque limiter: the displacement is capped at T_max/(D*dp)"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 1.0e-12, description = "Pressure band that rounds |dp| in the friction torque and the torque limiter"]
        w_tr::Real = 1.0, [unit = "rad/s", min = 1.0e-12, description = "Speed band over which the friction torque changes sign"]
    end
    @variables begin
        w::Real = 0.0, [unit = "rad/s", description = "Shaft speed"]
        dp::Real = 0.0, [unit = "Pa", description = "Pressure rise b minus a"]
        margin::Real = 0.0, [unit = "Pa", description = "LS margin b.e - ls.e"]
        x_ls::Real = 0.0, [unit = "1", description = "Displacement asked by the LS regulator"]
        x_pc::Real = 1.0, [unit = "1", description = "Displacement allowed by the pressure cut-off"]
        x_tq::Real = 1.0, [unit = "1", description = "Displacement allowed by the torque limiter"]
        x1::Real = 0.0, [unit = "1", description = "min(x_ls, x_pc)"]
        x::Real = 0.0, [unit = "1", description = "Displacement fraction, 0 to 1"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Delivered flow from a to b"]
        T::Real = 0.0, [unit = "N*m", description = "Shaft torque into the pump"]
        P_hyd::Real = 0.0, [unit = "W", description = "Hydraulic power delivered, dp*Q"]
        P_loss::Real = 0.0, [unit = "W", description = "Dissipated power (leakage plus friction)"]
    end
    # Signal outputs for readouts and energy meters: the displacement fraction, the shaft
    # (input) power T*w and the hydraulic (output) power dp*Q.
    @outputs begin
        xd::Real, [unit = "1"]
        P_in::Real, [unit = "W"]
        P_out::Real, [unit = "W"]
    end
    @equations begin
        w ~ shaft.f
        dp ~ b.e - a.e
        margin ~ b.e - ls.e
        # Smooth clamps to [0, 1] and a smooth min, as in CheckValve: (|s| - |s - 1| + 1)/2
        # and (a + b - |a - b|)/2 with |y| rounded as sqrt(y^2 + 1e-6).
        x_ls ~ 0.5 * (sqrt(((dp_ls + dp_reg - margin) / dp_reg)^2 + 1.0e-6) -
                      sqrt(((dp_ls - margin) / dp_reg)^2 + 1.0e-6) + 1.0)
        x_pc ~ 0.5 * (sqrt(((p_cut + dp_reg - dp) / dp_reg)^2 + 1.0e-6) -
                      sqrt(((p_cut - dp) / dp_reg)^2 + 1.0e-6) + 1.0)
        x_tq ~ T_max / (D * sqrt(dp * dp + p_tr * p_tr))
        x1 ~ 0.5 * (x_ls + x_pc - sqrt((x_ls - x_pc)^2 + 1.0e-6))
        x ~ 0.5 * (x1 + x_tq - sqrt((x1 - x_tq)^2 + 1.0e-6))
        Q ~ D * x * w - D * w_nom * (1.0 - eta_v) / p_nom * dp
        T ~ D * x * dp + D * (1.0 - eta_m) / eta_m * dp * tanh(dp / p_tr) * tanh(w / w_tr)
        P_hyd ~ dp * Q
        xd ~ x
        P_in ~ T * w
        P_out ~ P_hyd
        P_loss ~ D * w_nom * (1.0 - eta_v) / p_nom * dp * dp +
                 D * (1.0 - eta_m) / eta_m * dp * tanh(dp / p_tr) * tanh(w / w_tr) * w
        a.f ~ Q
        b.f ~ -Q
        shaft.e ~ T
        # The LS port is a pressure tap: no flow.
        ls.f ~ 0.0
    end
    @causality ls => (:flow_out, :fixed)
end
