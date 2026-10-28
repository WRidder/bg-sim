@block FixedTransform2D begin
    # The only legal bridge between two named frames (D-MB5): a = parent, b = child. Both
    # ports declare the frame their twist/wrench are expressed in, so a bond from a world
    # port to `a` and a bond from `b` to a body port check E007-clean.
    @ports begin
        a::Power{Planar}, [frame = "world"]
        b::Power{Planar}, [frame = "body"]
    end
    @parameters begin
        x::Real = 0.0, [unit = "m", description = "Child origin x in the parent frame"]
        y::Real = 0.0, [unit = "m", description = "Child origin y in the parent frame"]
        theta::Real = 0.0, [unit = "rad", description = "Child frame angle in the parent frame"]
    end
    @equations begin
        # g = (theta, x, y) maps child -> parent. Power continuity (a.e . a.f + b.e . b.f =
        # 0) fixes a.f = -Ad(g) b.f together with a.e = Ad(g)^-T b.e.
        a.f[1] ~ -b.f[1]
        a.f[2] ~ -(y * b.f[1] + cos(theta) * b.f[2] - sin(theta) * b.f[3])
        a.f[3] ~ x * b.f[1] - sin(theta) * b.f[2] - cos(theta) * b.f[3]
        a.e[1] ~ b.e[1] + (sin(theta) * x - cos(theta) * y) * b.e[2] +
                 (cos(theta) * x + sin(theta) * y) * b.e[3]
        a.e[2] ~ cos(theta) * b.e[2] - sin(theta) * b.e[3]
        a.e[3] ~ sin(theta) * b.e[2] + cos(theta) * b.e[3]
    end
    @causality (a, b) => :transformer
end
