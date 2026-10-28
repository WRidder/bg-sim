@block TFAd begin
    @ports begin
        a::Power{Planar}, [frame = "world"]
        b::Power{Planar}, [frame = "body"]
    end
    @inputs g::Vec{3}
    @equations begin
        # g = (theta, x, y) is the pose of b in a. With Ad(g) mapping a b-frame twist to
        # the a frame, power continuity a.e . a.f + b.e . b.f = 0 fixes BOTH signs:
        # a.f = -Ad(g) b.f and a.e = Ad(g)^-T b.e, equivalently b.e = Ad(g)^T a.e.
        #
        # FIX-MB-2: the effort relation is written in the causal direction of a
        # parent -> child chain (the a side faces the joint's 0-junction, the b side faces
        # the link). The two forms are exactly equivalent, but the explicit one has no 2x2
        # implicit rotation block, so MTK's alias elimination never divides by sin(theta)
        # (which is singular at theta = 0, the J-MB4 mounting-angle failure).
        a.f[1] ~ -b.f[1]
        a.f[2] ~ -(g[3] * b.f[1] + cos(g[1]) * b.f[2] - sin(g[1]) * b.f[3])
        a.f[3] ~ g[2] * b.f[1] - sin(g[1]) * b.f[2] - cos(g[1]) * b.f[3]
        b.e[1] ~ a.e[1] + g[3] * a.e[2] - g[2] * a.e[3]
        b.e[2] ~ cos(g[1]) * a.e[2] + sin(g[1]) * a.e[3]
        b.e[3] ~ -sin(g[1]) * a.e[2] + cos(g[1]) * a.e[3]
    end
    @causality (a, b) => :transformer
end
