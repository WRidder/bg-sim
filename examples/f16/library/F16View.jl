@block F16View begin
    # Scene helper (no physics): the 3D view keeps a reference aircraft framed by moving the
    # world instead of the camera. Every pose is relative to the reference aircraft's position:
    #
    #   pose       this aircraft: its attitude, at (its position - the reference's) + offset
    #              (offset: a formation slot, so aircraft that start together do not overlap)
    #   ground     a reference floor `depth` below the reference aircraft's start altitude z0, under
    #              the aircraft. It follows climbs and descents up to `reach` (then it stays in view as
    #              an attitude reference: a loop climbs a kilometre and more; the altitude is in the
    #              plots); it does not move sideways, so its edges stay put.
    #   stripes_x  the floor stripes across x (lines of constant x) and across y, at the floor's
    #   stripes_y  height. They scroll with the ground track, so the scene shows the speed although
    #              the aircraft stays put: each set moves along its own axis only, by the ground track
    #              wrapped into one stripe spacing `period` (-period/2 to period/2, 0 at the start), so
    #              the stripes stay on the floor. A wrap jumps by a whole period, which the pattern
    #              hides; the scene's bindings declare the period, so the 3D view interpolates across
    #              the wrap the short way instead of sliding the stripes back for a frame.
    #
    # For the reference aircraft itself (g = g0, offset 0) `pose` keeps it at the origin.
    @inputs begin
        g::Vec{7}, [description = "Pose of this aircraft (qw, qx, qy, qz, x, y, z), geometric body frame"]
        g0::Vec{7}, [description = "Pose of the reference aircraft"]
    end
    @outputs begin
        pose::Vec{7}, [description = "Pose of this aircraft in the view"]
        ground::Vec{7}, [description = "Pose of the floor in the view"]
        stripes_x::Vec{7}, [description = "Pose of the floor stripes across x in the view"]
        stripes_y::Vec{7}, [description = "Pose of the floor stripes across y in the view"]
    end
    @parameters begin
        dx::Real = 0.0, [unit = "m", description = "Formation offset, x (north)"]
        dy::Real = 0.0, [unit = "m", description = "Formation offset, y (west)"]
        dz::Real = 0.0, [unit = "m", description = "Formation offset, z (up)"]
        z0::Real = 0.0, [unit = "m", description = "Start altitude of the reference aircraft"]
        depth::Real = 150.0, [unit = "m", description = "Floor depth below the start altitude"]
        reach::Real = 100.0, [unit = "m", min = 0, description = "Largest climb or descent the floor follows"]
        period::Real = 100.0, [unit = "m", min = 1.0e-3, description = "Floor stripe spacing"]
    end
    @variables begin
        zf::Real = 0.0, [unit = "m", description = "Floor height in the view"]
    end
    @equations begin
        pose[1] ~ g[1]
        pose[2] ~ g[2]
        pose[3] ~ g[3]
        pose[4] ~ g[4]
        pose[5] ~ g[5] - g0[5] + dx
        pose[6] ~ g[6] - g0[6] + dy
        pose[7] ~ g[7] - g0[7] + dz
        zf ~ clamp(z0 - g0[7], -reach, reach) - depth
        ground[1] ~ 1.0
        ground[2] ~ 0.0
        ground[3] ~ 0.0
        ground[4] ~ 0.0
        ground[5] ~ 0.0
        ground[6] ~ 0.0
        ground[7] ~ zf
        stripes_x[1] ~ 1.0
        stripes_x[2] ~ 0.0
        stripes_x[3] ~ 0.0
        stripes_x[4] ~ 0.0
        stripes_x[5] ~ period * floor((g0[5] + period / 2) / period) - g0[5]
        stripes_x[6] ~ 0.0
        stripes_x[7] ~ zf
        stripes_y[1] ~ 1.0
        stripes_y[2] ~ 0.0
        stripes_y[3] ~ 0.0
        stripes_y[4] ~ 0.0
        stripes_y[5] ~ 0.0
        stripes_y[6] ~ period * floor((g0[6] + period / 2) / period) - g0[6]
        stripes_y[7] ~ zf
    end
end
