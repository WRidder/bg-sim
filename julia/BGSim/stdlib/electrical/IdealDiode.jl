@block IdealDiode begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @parameters begin
        R_on::Real = 1.0e-3, [unit = "Ohm", min = 1.0e-12, description = "On-state resistance"]
        G_off::Real = 1.0e-9, [unit = "1/Ohm", min = 0, description = "Residual off-state conductance (0 for an ideal open circuit)"]
        V_knee::Real = 0.0, [unit = "V", description = "Forward voltage above which the diode conducts"]
    end
    @equations begin
        p.f + n.f ~ 0.0
        # Piecewise-linear diode: `ifelse` is the non-smooth form the event collector sees, so
        # the crossing of `V_knee` lands on a switching instant (plan 5.8, J2.3).
        p.f ~ ifelse(
            p.e - n.e > V_knee,
            (p.e - n.e - V_knee) / R_on,
            G_off * (p.e - n.e),
        )
    end
end
