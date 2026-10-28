@block ScrewTF begin
    @ports begin
        a::Power{Planar}
        b::Power{Rotation}
    end
    @parameters begin
        rx::Real = 0.0, [unit = "m", description = "Joint axis point x in the parent frame"]
        ry::Real = 0.0, [unit = "m", description = "Joint axis point y in the parent frame"]
    end
    @equations begin
        # S = [1, ry, -rx] is the planar revolute screw (plan 3.1). Power continuity with
        # a.f = S*b.f requires b.e = -S^T a.e, not +S^T*.
        a.f[1] ~ b.f
        a.f[2] ~ ry * b.f
        a.f[3] ~ -rx * b.f
        b.e ~ -(a.e[1] + ry * a.e[2] - rx * a.e[3])
    end
    @causality (a, b) => :transformer
end
