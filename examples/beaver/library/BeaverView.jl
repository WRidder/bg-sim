@block BeaverView begin
    # Scene helper (no physics): the 3D view keeps a reference aircraft framed by moving the
    # world instead of the camera. Every pose is relative to the reference aircraft's position:
    #
    #   pose    this aircraft: its attitude, at (its position - the reference's) + offset
    #           (offset: a formation slot, so aircraft that start together do not overlap)
    #   ground  a reference floor `depth` below the reference aircraft's start altitude z0. It
    #           follows climbs and descents up to `reach` (then it stays in view as an attitude
    #           reference: a loop climbs a kilometre and more; the altitude is in the plots), and
    #           its pattern (period `period`, the spacing of the floor stripes) scrolls with the
    #           ground track, so the scene shows the speed although the aircraft stays put.
    #
    # For the reference aircraft itself (g = g0, offset 0) `pose` keeps it at the origin.
    @inputs begin
        g::Vec{7}, [description = "Pose of this aircraft (qw, qx, qy, qz, x, y, z), geometric body frame"]
        g0::Vec{7}, [description = "Pose of the reference aircraft"]
    end
    @outputs begin
        pose::Vec{7}, [description = "Pose of this aircraft in the view"]
        ground::Vec{7}, [description = "Pose of the floor pattern in the view"]
    end
    @parameters begin
        dx::Real = 0.0, [unit = "m", description = "Formation offset, x (north)"]
        dy::Real = 0.0, [unit = "m", description = "Formation offset, y (west)"]
        dz::Real = 0.0, [unit = "m", description = "Formation offset, z (up)"]
        z0::Real = 0.0, [unit = "m", description = "Start altitude of the reference aircraft"]
        depth::Real = 150.0, [unit = "m", description = "Floor depth below the start altitude"]
        reach::Real = 100.0, [unit = "m", min = 0, description = "Largest climb or descent the floor follows"]
        period::Real = 100.0, [unit = "m", min = 1.0e-3, description = "Floor pattern period"]
    end
    @equations begin
        pose[1] ~ g[1]
        pose[2] ~ g[2]
        pose[3] ~ g[3]
        pose[4] ~ g[4]
        pose[5] ~ g[5] - g0[5] + dx
        pose[6] ~ g[6] - g0[6] + dy
        pose[7] ~ g[7] - g0[7] + dz
        ground[1] ~ 1.0
        ground[2] ~ 0.0
        ground[3] ~ 0.0
        ground[4] ~ 0.0
        ground[5] ~ -(g0[5] - period * floor(g0[5] / period))
        ground[6] ~ -(g0[6] - period * floor(g0[6] / period))
        ground[7] ~ clamp(z0 - g0[7], -reach, reach) - depth
    end
end
