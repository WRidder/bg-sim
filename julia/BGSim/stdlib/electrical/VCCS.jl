@block VCCS begin
    @ports begin
        p1::Power{Electrical}
        n1::Power{Electrical}
        p2::Power{Electrical}
        n2::Power{Electrical}
    end
    @parameters transconductance::Real = 1.0, [unit = "1/Ohm", description = "Transconductance: the current p2.f = transconductance * v1"]
    @equations begin
        # Voltage-controlled current source: the controlling side p1-n1 is an open circuit
        # that senses v1, the controlled side p2-n2 imposes the current from p2 to n2.
        p1.f ~ 0.0
        p1.f + n1.f ~ 0.0
        p2.f ~ transconductance * (p1.e - n1.e)
        p2.f + n2.f ~ 0.0
    end
end
