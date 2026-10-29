@block JointTransform3D begin
    # The **joint-role** spatial frame transform (the plan's `JointTransform` for the spatial
    # domain): the same adjoint equations as `FixedTransform3D`, with the pose supplied as a
    # `Vec{7}` signal on the D-MB6 chart `(q_w, q_x, q_y, q_z, p_x, p_y, p_z)`.
    #
    # Both ports are **frame-neutral** (D-MB5: null unifies with any adjacent frame), exactly
    # like `TFAdNeutral` and the J-MB6 planar `JointTransform2D`. A joint composite must be
    # able to bond `a` to a body 1-junction (`ISpatial`'s frame is `body`) or to
    # `GroundSpatial` (`world`), and `b` to the child body; naming the sides
    # `parent`/`child` would make every such bond E007 because a body port is `body`. The
    # two ports are **separate** frame unions bridged by this block, so `a` adopting one body
    # and `b` another does not unify the two bodies' frames — that is exactly the transform
    # bridge DEC-MB-1 defines.
    #
    # `g` is the child pose in the parent frame. With `Ad(g)` mapping a child twist to the
    # parent frame, power continuity fixes both signs:
    #
    #     a.f = -Ad(g) b.f,        b.e = Ad(g)^T a.e,
    #
    # written in the explicit causal direction (b.e from a.e) exactly like
    # `FixedTransform3D` and `TFAd`, so no implicit rotation block reaches MTK's alias
    # elimination.
    #
    # v1 limitation (D-MB5): a `frame` value is a string literal, not a parameter, so a
    # multi-joint chain cannot rename roles per instance; typed frame objects are deferred
    # with the dependent-frame type system. The joint coordinate enters through the pose
    # signal a joint composite supplies, not through this block.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @inputs g::Vec{7}
    @variables begin
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation block of the input pose"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        a.f[1] ~ -(R[1, 1] * b.f[1] + R[1, 2] * b.f[2] + R[1, 3] * b.f[3])
        a.f[2] ~ -(R[2, 1] * b.f[1] + R[2, 2] * b.f[2] + R[2, 3] * b.f[3])
        a.f[3] ~ -(R[3, 1] * b.f[1] + R[3, 2] * b.f[2] + R[3, 3] * b.f[3])
        a.f[4] ~ -((g[6] * R[3, 1] - g[7] * R[2, 1]) * b.f[1] +
                   (g[6] * R[3, 2] - g[7] * R[2, 2]) * b.f[2] +
                   (g[6] * R[3, 3] - g[7] * R[2, 3]) * b.f[3] +
                   R[1, 1] * b.f[4] + R[1, 2] * b.f[5] + R[1, 3] * b.f[6])
        a.f[5] ~ -((g[7] * R[1, 1] - g[5] * R[3, 1]) * b.f[1] +
                   (g[7] * R[1, 2] - g[5] * R[3, 2]) * b.f[2] +
                   (g[7] * R[1, 3] - g[5] * R[3, 3]) * b.f[3] +
                   R[2, 1] * b.f[4] + R[2, 2] * b.f[5] + R[2, 3] * b.f[6])
        a.f[6] ~ -((g[5] * R[2, 1] - g[6] * R[1, 1]) * b.f[1] +
                   (g[5] * R[2, 2] - g[6] * R[1, 2]) * b.f[2] +
                   (g[5] * R[2, 3] - g[6] * R[1, 3]) * b.f[3] +
                   R[3, 1] * b.f[4] + R[3, 2] * b.f[5] + R[3, 3] * b.f[6])
        b.e[1] ~ R[1, 1] * (a.e[1] - (g[6] * a.e[6] - g[7] * a.e[5])) +
                 R[2, 1] * (a.e[2] - (g[7] * a.e[4] - g[5] * a.e[6])) +
                 R[3, 1] * (a.e[3] - (g[5] * a.e[5] - g[6] * a.e[4]))
        b.e[2] ~ R[1, 2] * (a.e[1] - (g[6] * a.e[6] - g[7] * a.e[5])) +
                 R[2, 2] * (a.e[2] - (g[7] * a.e[4] - g[5] * a.e[6])) +
                 R[3, 2] * (a.e[3] - (g[5] * a.e[5] - g[6] * a.e[4]))
        b.e[3] ~ R[1, 3] * (a.e[1] - (g[6] * a.e[6] - g[7] * a.e[5])) +
                 R[2, 3] * (a.e[2] - (g[7] * a.e[4] - g[5] * a.e[6])) +
                 R[3, 3] * (a.e[3] - (g[5] * a.e[5] - g[6] * a.e[4]))
        b.e[4] ~ R[1, 1] * a.e[4] + R[2, 1] * a.e[5] + R[3, 1] * a.e[6]
        b.e[5] ~ R[1, 2] * a.e[4] + R[2, 2] * a.e[5] + R[3, 2] * a.e[6]
        b.e[6] ~ R[1, 3] * a.e[4] + R[2, 3] * a.e[5] + R[3, 3] * a.e[6]
    end
    @causality (a, b) => :transformer
end
