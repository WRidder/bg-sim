@block IdealSwitch begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @inputs ctrl::Bool, [description = "Closed while true"]
    @parameters begin
        R_on::Real = 1.0e-3, [unit = "Ohm", min = 1.0e-12, description = "On-state resistance"]
        G_off::Real = 1.0e-9, [unit = "1/Ohm", min = 0, description = "Off-state conductance (0 for an ideal open circuit)"]
    end
    @equations begin
        p.f + n.f ~ 0.0
        # `ctrl == true` is the Bool comparison form of `ctrl`: a Bool signal is a real 0/1
        # parameter in the lowered system, and MTK's `ifelse` needs a Bool condition. The
        # comparison also gives the event collector a real switching condition (`ctrl - 1`).
        p.f ~ ifelse(ctrl == true, (p.e - n.e) / R_on, G_off * (p.e - n.e))
    end
end
