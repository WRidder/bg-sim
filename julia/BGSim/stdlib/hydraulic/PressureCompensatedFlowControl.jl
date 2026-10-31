@block PressureCompensatedFlowControl begin
    # 2-way pressure-compensated flow control valve between a and b: a throttle set by the
    # signal input u (0 to 1) behind a compensator that holds the throttle pressure drop at
    # dp_c. Above dp_c the flow is Q_nom*u whatever the load pressure; below dp_c the
    # compensator is wide open and the throttle sees the whole drop, so the flow falls off
    # like an orifice, Q_nom*u*sqrt(dp/dp_c). As formulas, with the throttle drop
    #   m = dp/(1 + (dp/dp_c)^8)^(1/8)          (a smooth, odd min(|dp|, dp_c))
    # and g(x) = x/(x^2 + p_tr^2)^(1/4) the orifice's regularized square root,
    #   Q = Q_nom*u*g(m)/g(dp_c),
    # smooth through dp = 0 and without a switching event. The valve is symmetric: a
    # reverse drop is regulated to -Q_nom*u the same way.
    @ports begin
        a::Power{Hydraulic}
        b::Power{Hydraulic}
    end
    @inputs u::Real
    @parameters begin
        Q_nom::Real = 1.0e-4, [unit = "m^3/s", min = 0, description = "Regulated flow at u = 1"]
        dp_c::Real = 1.0e6, [unit = "Pa", min = 1.0e-12, description = "Compensator pressure drop: the flow is regulated above it"]
        p_tr::Real = 1.0e5, [unit = "Pa", min = 1.0e-12, description = "Transition pressure of the orifice regularization"]
    end
    @variables begin
        dp::Real = 0.0, [unit = "Pa", description = "Pressure drop a minus b"]
        m::Real = 0.0, [unit = "Pa", description = "Pressure drop across the throttle"]
        Q::Real = 0.0, [unit = "m^3/s", description = "Flow from a to b"]
    end
    @equations begin
        dp ~ a.e - b.e
        m ~ dp / (1.0 + (dp / dp_c)^8)^0.125
        Q ~ Q_nom * u * m / dp_c *
            sqrt(sqrt(dp_c * dp_c + p_tr * p_tr) / sqrt(m * m + p_tr * p_tr))
        a.f ~ Q
        b.f ~ -Q
    end
end
