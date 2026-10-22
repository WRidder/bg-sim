@block Resistor begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @parameters R::Real = 1000.0, [unit = "Ohm", min = 0, description = "Resistance"]
    @equations begin
        p.f + n.f ~ 0.0
        p.e - n.e ~ R * p.f
    end
end
