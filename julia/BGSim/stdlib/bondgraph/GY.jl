@block GY begin
    @ports begin
        p1::Power{Generic}
        p2::Power{Generic}
    end
    @parameters r::Real = 1.0, [unit = "effort/flow", description = "Gyrator modulus"]
    @equations begin
        # Power-positive-into-each-port (spec): e1*f1 + e2*f2 = 0, so one effort is negative.
        p1.e ~ r * p2.f
        p2.e ~ -r * p1.f
    end
    @causality (p1, p2) => :gyrator
end
