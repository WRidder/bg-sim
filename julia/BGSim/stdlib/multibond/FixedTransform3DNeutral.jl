@block FixedTransform3DNeutral begin
    # Frame-neutral constant spatial mount: the `FixedTransform3D` equations with **both**
    # ports left frame-neutral (D-MB5: null unifies with any adjacent frame). It is the
    # body -> body mount (and the neutral mount inside a composite) that
    # `FixedTransform3D` cannot express: that block names its sides `world`/`body`, which is
    # the checked world -> body form.
    #
    # The two ports are **separate** frame unions bridged by this block, so `a` adopting one
    # body frame and `b` another does not unify the two bodies' frames; the transform is the
    # bridge, exactly as `TFAdNeutral` is for the planar domain (FIX-MB-4).
    #
    # The constant pose `g = (q_w, q_x, q_y, q_z, x, y, z)` is the child pose in the parent
    # frame (the D-MB6 chart, quaternion first). With the angular-first `Ad(g)` of
    # `src/mech/se3.jl`, `Ad(g) = [[R, 0], [p_hat R, R]]` maps a child twist to the parent
    # frame, and power continuity `a.e . a.f + b.e . b.f = 0` fixes both signs:
    #
    #     a.f = -Ad(g) b.f,        b.e = Ad(g)^T a.e.
    #
    # The effort relation is written in that explicit causal direction (b.e from a.e), like
    # `FixedTransform3D`/`TFAd` (FIX-MB-2), with no implicit rotation block.
    @ports begin
        a::Power{Spatial}
        b::Power{Spatial}
    end
    @parameters begin
        qw::Real = 1.0, [unit = "1", description = "Pose quaternion scalar part (child in parent)"]
        qx::Real = 0.0, [unit = "1", description = "Pose quaternion x"]
        qy::Real = 0.0, [unit = "1", description = "Pose quaternion y"]
        qz::Real = 0.0, [unit = "1", description = "Pose quaternion z"]
        x::Real = 0.0, [unit = "m", description = "Child origin x in the parent frame"]
        y::Real = 0.0, [unit = "m", description = "Child origin y in the parent frame"]
        z::Real = 0.0, [unit = "m", description = "Child origin z in the parent frame"]
    end
    @variables begin
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation block of the constant pose"]
    end
    @equations begin
        s ~ qw * qw + qx * qx + qy * qy + qz * qz
        R[1, 1] ~ (qw * qw + qx * qx - qy * qy - qz * qz) / s
        R[1, 2] ~ 2 * (qx * qy - qw * qz) / s
        R[1, 3] ~ 2 * (qx * qz + qw * qy) / s
        R[2, 1] ~ 2 * (qx * qy + qw * qz) / s
        R[2, 2] ~ (qw * qw - qx * qx + qy * qy - qz * qz) / s
        R[2, 3] ~ 2 * (qy * qz - qw * qx) / s
        R[3, 1] ~ 2 * (qx * qz - qw * qy) / s
        R[3, 2] ~ 2 * (qy * qz + qw * qx) / s
        R[3, 3] ~ (qw * qw - qx * qx - qy * qy + qz * qz) / s
        # a.f = -Ad(g) b.f, with the p_hat R rows written out: (p x R[j,:]) = p x (R b.f_ang).
        a.f[1] ~ -(R[1, 1] * b.f[1] + R[1, 2] * b.f[2] + R[1, 3] * b.f[3])
        a.f[2] ~ -(R[2, 1] * b.f[1] + R[2, 2] * b.f[2] + R[2, 3] * b.f[3])
        a.f[3] ~ -(R[3, 1] * b.f[1] + R[3, 2] * b.f[2] + R[3, 3] * b.f[3])
        a.f[4] ~ -((y * R[3, 1] - z * R[2, 1]) * b.f[1] +
                   (y * R[3, 2] - z * R[2, 2]) * b.f[2] +
                   (y * R[3, 3] - z * R[2, 3]) * b.f[3] +
                   R[1, 1] * b.f[4] + R[1, 2] * b.f[5] + R[1, 3] * b.f[6])
        a.f[5] ~ -((z * R[1, 1] - x * R[3, 1]) * b.f[1] +
                   (z * R[1, 2] - x * R[3, 2]) * b.f[2] +
                   (z * R[1, 3] - x * R[3, 3]) * b.f[3] +
                   R[2, 1] * b.f[4] + R[2, 2] * b.f[5] + R[2, 3] * b.f[6])
        a.f[6] ~ -((x * R[2, 1] - y * R[1, 1]) * b.f[1] +
                   (x * R[2, 2] - y * R[1, 2]) * b.f[2] +
                   (x * R[2, 3] - y * R[1, 3]) * b.f[3] +
                   R[3, 1] * b.f[4] + R[3, 2] * b.f[5] + R[3, 3] * b.f[6])
        # b.e = Ad(g)^T a.e: the angular row carries the lever term p x a.e_lin.
        b.e[1] ~ R[1, 1] * (a.e[1] - (y * a.e[6] - z * a.e[5])) +
                 R[2, 1] * (a.e[2] - (z * a.e[4] - x * a.e[6])) +
                 R[3, 1] * (a.e[3] - (x * a.e[5] - y * a.e[4]))
        b.e[2] ~ R[1, 2] * (a.e[1] - (y * a.e[6] - z * a.e[5])) +
                 R[2, 2] * (a.e[2] - (z * a.e[4] - x * a.e[6])) +
                 R[3, 2] * (a.e[3] - (x * a.e[5] - y * a.e[4]))
        b.e[3] ~ R[1, 3] * (a.e[1] - (y * a.e[6] - z * a.e[5])) +
                 R[2, 3] * (a.e[2] - (z * a.e[4] - x * a.e[6])) +
                 R[3, 3] * (a.e[3] - (x * a.e[5] - y * a.e[4]))
        b.e[4] ~ R[1, 1] * a.e[4] + R[2, 1] * a.e[5] + R[3, 1] * a.e[6]
        b.e[5] ~ R[1, 2] * a.e[4] + R[2, 2] * a.e[5] + R[3, 2] * a.e[6]
        b.e[6] ~ R[1, 3] * a.e[4] + R[2, 3] * a.e[5] + R[3, 3] * a.e[6]
    end
    @causality (a, b) => :transformer
end
