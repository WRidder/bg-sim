@block VoltageSensor begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @outputs y::Real = 0.0, [unit = "V"]
    @equations begin
        # An open-circuit sensor: it draws no current and reads the terminal voltage.
        p.f ~ 0.0
        n.f ~ 0.0
        y ~ p.e - n.e
    end
end
