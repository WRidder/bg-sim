@block CCVS begin
    @ports begin
        p1::Power{Electrical}
        n1::Power{Electrical}
        p2::Power{Electrical}
        n2::Power{Electrical}
    end
    @parameters transresistance::Real = 1.0, [unit = "Ohm", description = "Transresistance: v2 = transresistance * i1, with i1 = p1.f"]
    @equations begin
        # Current-controlled voltage source: the controlling side p1-n1 is a short circuit
        # that senses the current i1 from p1 to n1, the controlled side p2-n2 imposes v2.
        p1.e - n1.e ~ 0.0
        p1.f + n1.f ~ 0.0
        p2.e - n2.e ~ transresistance * p1.f
        p2.f + n2.f ~ 0.0
    end
end
