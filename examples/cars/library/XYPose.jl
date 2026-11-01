@block XYPose begin
    # A pose at a horizontal position, level (identity orientation, height 0): the query pose of
    # a `TerrainSurface` that only needs (x, y), e.g. to read the terrain height under a tyre's
    # contact point.
    @inputs begin
        x::Real, [unit = "m", description = "World x"]
        y::Real, [unit = "m", description = "World y"]
    end
    @outputs g::Vec{7}, [description = "Pose (1, 0, 0, 0, x, y, 0)"]
    @equations begin
        g[1] ~ 1.0
        g[2] ~ 0.0
        g[3] ~ 0.0
        g[4] ~ 0.0
        g[5] ~ x
        g[6] ~ y
        g[7] ~ 0.0
    end
end
