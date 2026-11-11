@block Battery begin
    @constants N::Int = 5
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @parameters begin
        capacity::Real = 2.0, [unit = "A*h", min = 1.0e-12, description = "Charge capacity"]
        soc_table::Vec{N} = [0.0, 0.1, 0.5, 0.9, 1.0], [unit = "1", description = "State-of-charge breakpoints of the OCV table, strictly increasing"]
        ocv_table::Vec{N} = [3.0, 3.45, 3.7, 4.0, 4.2], [unit = "V", description = "Open-circuit voltage at every state-of-charge breakpoint"]
        R0::Real = 0.05, [unit = "Ohm", min = 0, description = "Series (ohmic) resistance"]
        R1::Real = 0.02, [unit = "Ohm", min = 1.0e-12, description = "Resistance of the polarisation RC pair"]
        C1::Real = 1000.0, [unit = "F", min = 1.0e-12, description = "Capacitance of the polarisation RC pair"]
    end
    @constants seconds_per_hour::Real = 3600.0, [unit = "s/h", description = "Converts the capacity from A*h to A*s"]
    @variables begin
        soc::Real = 1.0, [unit = "1", state = :prefer, description = "State of charge, 1 full and 0 empty; the start value is the initial charge"]
        v1::Real = 0.0, [unit = "V", state = :prefer, description = "Voltage over the polarisation RC pair"]
        ocv::Real = 0.0, [unit = "V", description = "Open-circuit voltage at the present state of charge"]
    end
    @equations begin
        # The charging current p.f (positive into p) fills the charge; the OCV is a table
        # over the state of charge (held at the edge values outside it).
        p.f + n.f ~ 0.0
        ddt(soc) ~ p.f / (capacity * seconds_per_hour)
        ocv ~ interp1(soc, soc_table, ocv_table)
        # Thevenin equivalent circuit: OCV, the series R0 and one RC pair. The heat in R0
        # and R1 would go to a later thermal port.
        ddt(v1) ~ (p.f - v1 / R1) / C1
        p.e - n.e ~ ocv + R0 * p.f + v1
    end
    @orientation begin
        p => :in
        n => :in
    end
end
