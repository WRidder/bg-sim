@block IdealTransformer begin
    @ports begin
        p1::Power{Electrical}
        n1::Power{Electrical}
        p2::Power{Electrical}
        n2::Power{Electrical}
    end
    @parameters n::Real = 1.0, [min = 1.0e-12, description = "Turns ratio: p1-side winding voltage over p2-side winding voltage"]
    @equations begin
        # Lossless two-winding transformer with power positive into each winding:
        # v1 = n * v2 and p1.f = -p2.f / n, so v1*i1 + v2*i2 = 0.
        p1.f + n1.f ~ 0.0
        p2.f + n2.f ~ 0.0
        p1.e - n1.e ~ n * (p2.e - n2.e)
        p2.f ~ -n * p1.f
    end
end
