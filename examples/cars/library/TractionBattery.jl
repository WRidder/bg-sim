@block TractionBattery begin
    # Traction battery pack: an open-circuit voltage that rises linearly with the state of
    # charge, a series internal resistance and the charge as the one state. Power positive into
    # the port (p.f is the CHARGING current): p.e = ocv + R p.f, soc' = p.f / (Q 3600). The
    # outputs report the discharge side (current and power positive when the pack drives).
    # Losses R p.f^2 >= 0; the stored energy is the integral of ocv over the charge.
    @ports p::Power{Electrical}
    @outputs begin
        soc::Real, [unit = "1", description = "State of charge, 1 full"]
        ocv::Real, [unit = "V", description = "Open-circuit voltage"]
        V::Real, [unit = "V", description = "Terminal voltage"]
        I::Real, [unit = "A", description = "Discharge current (positive when driving)"]
        P::Real, [unit = "W", description = "Discharge power at the terminals"]
    end
    @parameters begin
        Q::Real = 100.0, [unit = "A*h", min = 1.0e-6, description = "Capacity"]
        V_empty::Real = 340.0, [unit = "V", min = 0, description = "Open-circuit voltage at soc = 0"]
        V_full::Real = 403.0, [unit = "V", min = 0, description = "Open-circuit voltage at soc = 1"]
        R::Real = 0.06, [unit = "Ohm", min = 0, description = "Internal resistance"]
        k_h::Real = 3600.0, [unit = "s/h", description = "Seconds per hour"]
    end
    @variables x::Real = 0.9, [unit = "1", state = :prefer, description = "State of charge (the state)"]
    @equations begin
        ddt(x) ~ p.f / (Q * k_h)
        soc ~ x
        ocv ~ V_empty + (V_full - V_empty) * x
        p.e ~ ocv + R * p.f
        V ~ p.e
        I ~ -p.f
        P ~ -p.e * p.f
    end
end
