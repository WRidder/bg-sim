@block IGBT begin
    @ports begin
        c::Power{Electrical}
        e::Power{Electrical}
    end
    @inputs gate::Bool, [description = "Switch on while true"]
    @parameters begin
        R_on::Real = 1.0e-2, [unit = "Ohm", min = 1.0e-12, description = "Collector-emitter on-state resistance"]
        V_ce0::Real = 0.0, [unit = "V", min = 0, description = "Collector-emitter knee voltage above which the switch conducts"]
        G_off::Real = 1.0e-9, [unit = "1/Ohm", min = 0, description = "Off-state conductance (0 for an ideal open circuit)"]
        V_f::Real = 0.7, [unit = "V", description = "Forward voltage of the antiparallel freewheeling diode (emitter to collector)"]
        R_d::Real = 1.0e-2, [unit = "Ohm", min = 1.0e-12, description = "On-state resistance of the freewheeling diode"]
    end
    @variables begin
        v::Real = 0.0, [unit = "V", description = "Collector-emitter voltage"]
        i_sw::Real = 0.0, [unit = "A", description = "Switch current from c to e"]
        i_diode::Real = 0.0, [unit = "A", description = "Freewheeling-diode current from e to c"]
    end
    @equations begin
        c.f + e.f ~ 0.0
        v ~ c.e - e.e
        # A one-way switch: it conducts from c to e above the knee V_ce0 while the gate is
        # true, and blocks otherwise (G_off). The freewheeling diode is IdealDiode from e
        # to c. The conduction losses would go to a later thermal port.
        i_sw ~ ifelse(gate == true, ifelse(v > V_ce0, (v - V_ce0) / R_on, G_off * v), G_off * v)
        i_diode ~ ifelse(-v > V_f, (-v - V_f) / R_d, 0.0)
        c.f ~ i_sw - i_diode
    end
    @orientation begin
        c => :in
        e => :in
    end
end
