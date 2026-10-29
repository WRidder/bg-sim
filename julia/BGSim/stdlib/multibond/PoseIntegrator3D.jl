@block PoseIntegrator3D begin
    # Floating-base spatial pose integrator (D-MB6): the pose is the state, on the chart
    # `Vec{7} = (q_w, q_x, q_y, q_z, p_x, p_y, p_z)` (quaternion first, then the body origin
    # in the world). The input is the **body twist** `tw = [w; v]` of the body whose pose this
    # is (the `twout` of `ISpatial`, or the `V` face of a floating body).
    #
    #     ddt(q) = 0.5 q (x) [0, w]          (q . qdot = 0 identically)
    #     ddt(p) = R(q) v
    #
    # Both are written component-wise with the unnormalised quadratic form of `R` divided by
    # `|q|^2`, the same expansion as `src/lower/fnmap.jl`'s `_quat_matrix`: `q` stays unit to
    # the solver's accuracy (the RHS is orthogonal to `q`), so `|q|^2 = 1` and `R` is the
    # rotation. There is no `exp` integrator and no implicit constraint: the pose is seven
    # states and the RHS is `q . qdot = 0`.
    #
    # Only a floating base uses this block: a fixed-base link's pose is algebraic,
    # `g_child = g_parent ∘ g(q)` (`ComposePose3D`/`JointTransform3D`), exactly the D-MB6 rule
    # and the planar `PoseIntegrator2D` convention. The initial pose is a set of start values,
    # which are outside the compile key (D4), so an initial-pose change is a cache hit.
    @inputs tw::Vec{6}, [description = "Body twist [w; v] of the body whose pose this is"]
    @variables begin
        qw::Real = 1.0, [unit = "1", state = :prefer, description = "Pose quaternion scalar part"]
        qx::Real = 0.0, [unit = "1", state = :prefer, description = "Pose quaternion x"]
        qy::Real = 0.0, [unit = "1", state = :prefer, description = "Pose quaternion y"]
        qz::Real = 0.0, [unit = "1", state = :prefer, description = "Pose quaternion z"]
        px::Real = 0.0, [unit = "m", state = :prefer, description = "Body origin x in the world"]
        py::Real = 0.0, [unit = "m", state = :prefer, description = "Body origin y in the world"]
        pz::Real = 0.0, [unit = "m", state = :prefer, description = "Body origin z in the world"]
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation matrix of the current quaternion"]
    end
    @outputs g::Vec{7}
    @equations begin
        # ddt(q) = 0.5 q (x) [0, w], scalar part first (D-MB6 / Mech.compose order).
        ddt(qw) ~ -0.5 * (tw[1] * qx + tw[2] * qy + tw[3] * qz)
        ddt(qx) ~ 0.5 * (tw[1] * qw + tw[3] * qy - tw[2] * qz)
        ddt(qy) ~ 0.5 * (tw[2] * qw + tw[1] * qz - tw[3] * qx)
        ddt(qz) ~ 0.5 * (tw[3] * qw + tw[2] * qx - tw[1] * qy)
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
        # ddt(p) = R(q) v.
        ddt(px) ~ R[1, 1] * tw[4] + R[1, 2] * tw[5] + R[1, 3] * tw[6]
        ddt(py) ~ R[2, 1] * tw[4] + R[2, 2] * tw[5] + R[2, 3] * tw[6]
        ddt(pz) ~ R[3, 1] * tw[4] + R[3, 2] * tw[5] + R[3, 3] * tw[6]
        g[1] ~ qw
        g[2] ~ qx
        g[3] ~ qy
        g[4] ~ qz
        g[5] ~ px
        g[6] ~ py
        g[7] ~ pz
    end
end
