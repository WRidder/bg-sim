@block JointTransform2D begin
    # The **joint-role** planar frame transform: `stdlib:multibond/JointTransform2D` is the
    # plan's `JointTransform` for the planar domain. It carries the same adjoint equations as
    # `TFAd` (component-wise `Ad(g)`), and it is the transform a joint uses to bridge its
    # parent-side and child-side frames: the two ports declare the joint role frames
    # `parent` and `child`, so a bond from a `parent`-frame port to `a` and from `b` to a
    # `child`-frame port is E007-clean, while any other named frame on those bonds is
    # reported (D-MB5: only a transform bridges frames).
    #
    # The pose input `g = (theta, x, y)` is the child pose in the parent frame. With `Ad(g)`
    # mapping a child twist to the parent frame, power continuity
    # `a.e . a.f + b.e . b.f = 0` fixes both signs: `a.f = -Ad(g) b.f` and
    # `a.e = Ad(g)^-T b.e`. Never copy one without the other.
    #
    # v1 limitation (D-MB5): a `frame` value is a string literal, not a parameter, so a
    # multi-joint chain cannot rename these two frames per instance; typed frame objects
    # (`SE2{:parent,:child}`) are deferred with the dependent-frame type system. The joint
    # *coordinate* enters through `ScrewTF`/the joint composite, not through this block.
    @ports begin
        a::Power{Planar}, [frame = "parent"]
        b::Power{Planar}, [frame = "child"]
    end
    @inputs g::Vec{3}
    @equations begin
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
