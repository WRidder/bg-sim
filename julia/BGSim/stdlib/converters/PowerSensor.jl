@block PowerSensor begin
    @ports begin
        a::Power{Generic}
        b::Power{Generic}
    end
    @outputs y::Real = 0.0, [unit = "effort*flow"]
    @equations begin
        # A transparent two-port on the bond whose power is measured. The output unit is
        # the D9 symbolic power unit; domain adoption turns it into W on a concrete island.
        a.f ~ b.f
        a.e ~ b.e
        y ~ a.e * a.f
    end
end
