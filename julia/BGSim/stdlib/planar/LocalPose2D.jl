@block LocalPose2D begin
    # A constant SE(2) pose (theta, x, y): the local mounting pose of a link in its parent
    # frame. It is the `gl` argument of `ComposePose2D` (`g_link = g_joint ∘ g_local`), so a
    # fixed-base chain composes its poses algebraically instead of integrating them (D-MB6).
    @parameters begin
        x::Real = 0.0, [unit = "m", description = "Local x"]
        y::Real = 0.0, [unit = "m", description = "Local y"]
        theta::Real = 0.0, [unit = "rad", description = "Local angle"]
    end
    @outputs g::Vec{3}
    @equations begin
        g[1] ~ theta
        g[2] ~ x
        g[3] ~ y
    end
end
