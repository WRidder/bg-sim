@block Fuselage begin
    # The fuselage of the Heffley & Mnich model (lines 6650 .. 6720), a modulated source applied
    # at the fuselage reference point: drag, side force and the heave force of the rotor
    # downwash, X = rho/2 XUU |u| u, Y = rho/2 YVV |v| v, Z = rho/2 ZWW |w - vi| (w - vi) (FRD).
    # The report's pitching moment uses the downwash centre of pressure D.FW (magnified 3x for
    # the A109) instead of the reference point, and has no yaw moment: the outputs add those
    # differences to the r x F the bond graph forms, so the sum is the report's.
    # |x| x is written x sqrt(x^2 + 1e-6) and u/(vi - w) as u (vi - w)/((vi - w)^2 + 1e-6): no
    # event at every sign change, the same numbers to 1e-9 m/s.
    @inputs begin
        u::Real
        v::Real
        w::Real
        vi::Real, [description = "Main-rotor induced velocity (m/s)"]
        rho::Real
    end
    @outputs begin
        tx::Real
        ty::Real
        tz::Real
        fx::Real
        fy::Real
        fz::Real
        p_para::Real, [description = "Parasite power -X u - Y v - Z (w - vi) (W)"]
    end
    @parameters begin
        XUU::Real = -1.0, [description = "Drag area (m^2)"]
        YVV::Real = -1.0, [description = "Side-force area (m^2)"]
        ZWW::Real = -1.0, [description = "Vertical drag area (m^2)"]
        h_hub::Real = 0.0, [description = "Hub height above the CG (m)"]
        h_fus::Real = 0.0, [description = "Fuselage point above the CG (m)"]
        d_fus::Real = 0.0, [description = "Fuselage point aft of the CG (m)"]
        d_hub::Real = 0.0, [description = "Hub aft of the CG (m)"]
        fw_gain::Real = 3.0, [description = "Magnification of the downwash centre-of-pressure shift (A109: 3)"]
    end
    @variables begin
        wa::Real = 0.0
        dfw::Real = 0.0, [description = "Downwash centre of pressure aft of the CG (m)"]
        X::Real = 0.0
        Y::Real = 0.0
        Z::Real = 0.0
    end
    @equations begin
        wa ~ w - vi
        dfw ~ fw_gain * (u * (-wa) / (wa * wa + 1.0e-6) * (h_hub - h_fus) - (d_fus - d_hub))
        X ~ 0.5 * rho * XUU * sqrt(u * u + 1.0e-6) * u
        Y ~ 0.5 * rho * YVV * sqrt(v * v + 1.0e-6) * v
        Z ~ 0.5 * rho * ZWW * sqrt(wa * wa + 1.0e-6) * wa
        fx ~ X
        fy ~ -Y
        fz ~ -Z
        tx ~ 0.0
        ty ~ -(Z * (dfw - d_fus))
        tz ~ -(d_fus * Y)
        p_para ~ -X * u - Y * v - Z * wa
    end
end
