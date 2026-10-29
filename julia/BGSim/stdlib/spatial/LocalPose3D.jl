@block LocalPose3D begin
    # A constant SE(3) pose on the D-MB6 chart `(q_w, q_x, q_y, q_z, x, y, z)`: the local
    # mounting pose of a link in its parent frame. It is the `gl` argument of
    # `ComposePose3D` (`g_link = g_joint composed with g_local`), so a fixed-base chain
    # composes its poses algebraically instead of integrating them (D-MB6).
    @parameters begin
        qw::Real = 1.0, [unit = "1", description = "Pose quaternion scalar part"]
        qx::Real = 0.0, [unit = "1", description = "Pose quaternion x"]
        qy::Real = 0.0, [unit = "1", description = "Pose quaternion y"]
        qz::Real = 0.0, [unit = "1", description = "Pose quaternion z"]
        x::Real = 0.0, [unit = "m", description = "Local x"]
        y::Real = 0.0, [unit = "m", description = "Local y"]
        z::Real = 0.0, [unit = "m", description = "Local z"]
    end
    @outputs g::Vec{7}
    @equations begin
        g[1] ~ qw
        g[2] ~ qx
        g[3] ~ qy
        g[4] ~ qz
        g[5] ~ x
        g[6] ~ y
        g[7] ~ z
    end
end
