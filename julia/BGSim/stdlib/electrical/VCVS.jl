@block VCVS begin
    @ports begin
        p1::Power{Electrical}
        n1::Power{Electrical}
        p2::Power{Electrical}
        n2::Power{Electrical}
    end
    @parameters gain::Real = 1.0, [unit = "1", description = "Voltage gain: v2 = gain * v1"]
    @equations begin
        # Voltage-controlled voltage source: the controlling side p1-n1 is an open circuit
        # that senses v1, the controlled side p2-n2 imposes v2.
        p1.f ~ 0.0
        p1.f + n1.f ~ 0.0
        p2.e - n2.e ~ gain * (p1.e - n1.e)
        p2.f + n2.f ~ 0.0
    end
end
