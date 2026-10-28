@block TFAd begin
    @ports begin
        a::Power{Planar}, [frame = "world"]
        b::Power{Planar}, [frame = "body"]
    end
    @inputs g::Vec{3}
    @equations begin
        # g = (theta, x, y) is the pose of b in a. With Ad(g) mapping a b-frame twist to
        # the a frame, power continuity a.e . a.f + b.e . b.f = 0 fixes BOTH signs:
        # a.f = -Ad(g) b.f and a.e = Ad(g)^-T b.e (the scalar TF's p1.e = n*p2.e,
        # p2.f = -n*p1.f). Never copy one of them without the other.
        a.f[1] ~ -b.f[1]
        a.f[2] ~ -(g[3] * b.f[1] + cos(g[1]) * b.f[2] - sin(g[1]) * b.f[3])
        a.f[3] ~ g[2] * b.f[1] - sin(g[1]) * b.f[2] - cos(g[1]) * b.f[3]
        a.e[1] ~ b.e[1] + (sin(g[1]) * g[2] - cos(g[1]) * g[3]) * b.e[2] +
                 (cos(g[1]) * g[2] + sin(g[1]) * g[3]) * b.e[3]
        a.e[2] ~ cos(g[1]) * b.e[2] - sin(g[1]) * b.e[3]
        a.e[3] ~ sin(g[1]) * b.e[2] + cos(g[1]) * b.e[3]
    end
    @causality (a, b) => :transformer
end
