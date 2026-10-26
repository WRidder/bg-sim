@block MTF begin
    @ports begin
        p1::Power{Generic}
        p2::Power{Generic}
    end
    @inputs u::Real
    @equations begin
        # Power-positive-into-each-port (spec): e1*f1 + e2*f2 = 0, so one flow is negative.
        # The modulus is the signal input u instead of a parameter (the modulated TF).
        p1.e ~ u * p2.e
        p2.f ~ -u * p1.f
    end
    @causality (p1, p2) => :transformer
end
