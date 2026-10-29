@block ComposePose3D begin
    # Spatial pose composition on the D-MB6 chart `(q_w, q_x, q_y, q_z, p_x, p_y, p_z)`:
    #
    #     g = gp composed with gl,     q = qp (x) ql,     p = p_p + R(qp) p_l,
    #
    # the same order as `Mech.compose`/`SE3 * SE3`. The fixed-base link pose is composed from
    # the joint coordinate, never integrated (D-MB6); only a floating base holds a pose state
    # (`PoseIntegrator3D`).
    #
    # The Hamilton product is written out and **not** renormalised or sign-canonicalised,
    # exactly like `compose(::Quat, ::Quat)` (a product of unit quaternions is unit to
    # rounding; `q` and `-q` are the same rotation). That is what lets a composed chain and an
    # integrated quaternion agree component by component over many turns.
    @inputs begin
        gp::Vec{7}
        gl::Vec{7}
    end
    @outputs g::Vec{7}
    @variables begin
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |qp|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation block of gp"]
    end
    @equations begin
        s ~ gp[1] * gp[1] + gp[2] * gp[2] + gp[3] * gp[3] + gp[4] * gp[4]
        R[1, 1] ~ (gp[1] * gp[1] + gp[2] * gp[2] - gp[3] * gp[3] - gp[4] * gp[4]) / s
        R[1, 2] ~ 2 * (gp[2] * gp[3] - gp[1] * gp[4]) / s
        R[1, 3] ~ 2 * (gp[2] * gp[4] + gp[1] * gp[3]) / s
        R[2, 1] ~ 2 * (gp[2] * gp[3] + gp[1] * gp[4]) / s
        R[2, 2] ~ (gp[1] * gp[1] - gp[2] * gp[2] + gp[3] * gp[3] - gp[4] * gp[4]) / s
        R[2, 3] ~ 2 * (gp[3] * gp[4] - gp[1] * gp[2]) / s
        R[3, 1] ~ 2 * (gp[2] * gp[4] - gp[1] * gp[3]) / s
        R[3, 2] ~ 2 * (gp[3] * gp[4] + gp[1] * gp[2]) / s
        R[3, 3] ~ (gp[1] * gp[1] - gp[2] * gp[2] - gp[3] * gp[3] + gp[4] * gp[4]) / s
        # Hamilton product qp (x) ql, scalar part first (same order as Mech.compose).
        g[1] ~ gp[1] * gl[1] - gp[2] * gl[2] - gp[3] * gl[3] - gp[4] * gl[4]
        g[2] ~ gp[1] * gl[2] + gp[2] * gl[1] + gp[3] * gl[4] - gp[4] * gl[3]
        g[3] ~ gp[1] * gl[3] - gp[2] * gl[4] + gp[3] * gl[1] + gp[4] * gl[2]
        g[4] ~ gp[1] * gl[4] + gp[2] * gl[3] - gp[3] * gl[2] + gp[4] * gl[1]
        # p = p_p + R(qp) p_l.
        g[5] ~ gp[5] + R[1, 1] * gl[5] + R[1, 2] * gl[6] + R[1, 3] * gl[7]
        g[6] ~ gp[6] + R[2, 1] * gl[5] + R[2, 2] * gl[6] + R[2, 3] * gl[7]
        g[7] ~ gp[7] + R[3, 1] * gl[5] + R[3, 2] * gl[6] + R[3, 3] * gl[7]
    end
end
