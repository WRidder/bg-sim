@block PowerSensor begin
    @ports begin
        a::Power{Generic}
        b::Power{Generic}
    end
    @outputs y::Real = 0.0, [unit = "effort*flow"]
    @equations begin
        # A transparent two-port on the bond whose power is measured: the effort passes
        # through and the flow that enters at `a` leaves at `b` (port flows count into the
        # block, so a.f + b.f = 0 and no power is stored or lost). The output is the power
        # entering at `a`, so with the bonds drawn through the sensor (half-arrows into `a`
        # and out of `b`) it is the power in the direction of the half-arrows. The output
        # unit is the D9 symbolic power unit; domain adoption turns it into W on a concrete
        # island.
        a.e ~ b.e
        a.f + b.f ~ 0.0
        y ~ a.e * a.f
    end
    @orientation (a, b) => :through
end
