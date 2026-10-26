@block MGY begin
    @ports begin
        p1::Power{Generic}
        p2::Power{Generic}
    end
    @inputs u::Real
    @equations begin
        # Power-positive-into-each-port (spec): e1*f1 + e2*f2 = 0, so one effort is negative.
        # Same orientation as GY: with p1 on the electrical side and p2 on the mechanical side
        # (the DC-motor bond graph of plan 9.1), this is the motor one. The modulus is the
        # signal input u instead of a parameter (the modulated GY).
        p1.e ~ -u * p2.f
        p2.e ~ u * p1.f
    end
    @causality (p1, p2) => :gyrator
end
