@block SumPa begin
    # Sum of the powers given to the air by the eight aerodynamic blocks (4 wing segments, 3 tail flaps,
    # the fuselage), and the cycle-averaged value (first-order low-pass of time constant `tau`).
    @inputs begin
        u1::Real
        u2::Real
        u3::Real
        u4::Real
        u5::Real
        u6::Real
        u7::Real
        u8::Real
    end
    @outputs begin
        P::Real, [unit = "W"]
        Pavg::Real, [unit = "W"]
    end
    @parameters tau::Real = 1.0, [unit = "s", min = 1.0e-3, description = "Averaging time constant"]
    @variables Pf::Real = 0.0, [unit = "W", description = "Low-passed power"]
    @equations begin
        P ~ u1 + u2 + u3 + u4 + u5 + u6 + u7 + u8
        ddt(Pf) ~ (P - Pf) / tau
        Pavg ~ Pf
    end
end
