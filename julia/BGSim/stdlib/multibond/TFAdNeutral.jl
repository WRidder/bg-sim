@block TFAdNeutral begin
    # Frame-neutral planar adjoint transformer: the `TFAd` equations with **both** ports left
    # frame-neutral (D-MB5: null unifies with any adjacent frame). `TFAd` names its two sides
    # `world`/`body`, which is right for an explicit frame bridge but wrong inside a joint
    # composite: the composite's parent role must be neutral so one instance can attach to
    # `GroundPlanar` (world) *and* to a body 1-junction as an elbow (FIX-MB-4). The child side
    # of the composite names its own frame, so a neutral `b` adopts it.
    #
    # g = (theta, x, y) is the pose of b in a. With `Ad(g)` mapping a b-frame twist to the a
    # frame, power continuity `a.e . a.f + b.e . b.f = 0` fixes BOTH signs:
    # `a.f = -Ad(g) b.f` and `a.e = Ad(g)^-T b.e`, equivalently `b.e = Ad(g)^T a.e`. As in
    # `TFAd`/`FixedJoint2D` (FIX-MB-2) the effort relation is written in the causal direction
    # of a parent -> child chain, so MTK's alias elimination never divides by `sin(theta)`.
    @ports begin
        a::Power{Planar}
        b::Power{Planar}
    end
    @inputs g::Vec{3}
    @equations begin
        a.f[1] ~ -b.f[1]
        a.f[2] ~ -(g[3] * b.f[1] + cos(g[1]) * b.f[2] - sin(g[1]) * b.f[3])
        a.f[3] ~ g[2] * b.f[1] - sin(g[1]) * b.f[2] - cos(g[1]) * b.f[3]
        b.e[1] ~ a.e[1] + g[3] * a.e[2] - g[2] * a.e[3]
        b.e[2] ~ cos(g[1]) * a.e[2] + sin(g[1]) * a.e[3]
        b.e[3] ~ -sin(g[1]) * a.e[2] + cos(g[1]) * a.e[3]
    end
    @causality (a, b) => :transformer
end
