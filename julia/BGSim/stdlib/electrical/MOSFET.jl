@block MOSFET begin
    @ports begin
        d::Power{Electrical}
        s::Power{Electrical}
    end
    @inputs gate::Bool, [description = "Channel on while true"]
    @parameters begin
        R_on::Real = 1.0e-2, [unit = "Ohm", min = 1.0e-12, description = "Drain-source on-state resistance (conducts both ways)"]
        G_off::Real = 1.0e-9, [unit = "1/Ohm", min = 0, description = "Off-state conductance (0 for an ideal open circuit)"]
        V_f::Real = 0.7, [unit = "V", description = "Forward voltage of the antiparallel body diode (source to drain)"]
        R_d::Real = 1.0e-2, [unit = "Ohm", min = 1.0e-12, description = "On-state resistance of the body diode"]
    end
    @variables begin
        v::Real = 0.0, [unit = "V", description = "Drain-source voltage"]
        i_ch::Real = 0.0, [unit = "A", description = "Channel current from d to s"]
        i_diode::Real = 0.0, [unit = "A", description = "Body-diode current from s to d"]
    end
    @equations begin
        d.f + s.f ~ 0.0
        v ~ d.e - s.e
        # The switching channel as in IdealSwitch (a Bool gate compared with `true`), and
        # the body diode as in IdealDiode, from s to d. Both are `ifelse` forms, so the
        # gate edges and the diode knee are switching instants. The conduction losses
        # would go to a later thermal port.
        i_ch ~ ifelse(gate == true, v / R_on, G_off * v)
        i_diode ~ ifelse(-v > V_f, (-v - V_f) / R_d, 0.0)
        d.f ~ i_ch - i_diode
    end
end
