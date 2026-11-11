@block CCCS begin
    @ports begin
        p1::Power{Electrical}
        n1::Power{Electrical}
        p2::Power{Electrical}
        n2::Power{Electrical}
    end
    @parameters gain::Real = 1.0, [unit = "1", description = "Current gain: p2.f = gain * i1, with i1 = p1.f"]
    @equations begin
        # Current-controlled current source: the controlling side p1-n1 is a short circuit
        # that senses the current i1 from p1 to n1, the controlled side p2-n2 imposes the
        # current from p2 to n2.
        p1.e - n1.e ~ 0.0
        p1.f + n1.f ~ 0.0
        p2.f ~ gain * p1.f
        p2.f + n2.f ~ 0.0
    end
    @orientation begin
        p1 => :in
        n1 => :in
        p2 => :in
        n2 => :in
    end
end
