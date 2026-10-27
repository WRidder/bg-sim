@block CurrentSensor begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @outputs y::Real = 0.0, [unit = "A"]
    @equations begin
        # A series sensor: zero voltage drop, and the current through it is the output.
        p.e - n.e ~ 0.0
        p.f ~ y
        p.f + n.f ~ 0.0
    end
end
