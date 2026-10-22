@block TF begin
    @ports begin
        p1::Power{Generic}
        p2::Power{Generic}
    end
    @parameters n::Real = 1.0, [min = 0, description = "Transformer modulus"]
    @equations begin
        p1.e ~ n * p2.e
        p2.f ~ n * p1.f
    end
    @causality (p1, p2) => :transformer
end
