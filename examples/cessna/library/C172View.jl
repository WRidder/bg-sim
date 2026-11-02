@block C172View begin
    # Scene helper (no physics): the 3D view keeps a reference aircraft framed by moving the
    # world instead of the camera (as the f16 example's F16View). Every pose is relative to the
    # reference aircraft's position g0 (for the reference itself, g = g0):
    #
    #   pose     this aircraft: its attitude, at (its position - the reference's) + (dx, dy, dz)
    #            (a formation slot, so aircraft that start together do not overlap)
    #   field    the airfield (runway, taxiway, buildings): the world shifted by -g0, so it stays
    #            where it is relative to the aircraft
    #   stripes  a striped reference floor for flight far from the field: `depth` below the start
    #            altitude z0, following climbs and descents up to `reach`, its pattern (period
    #            `period`) scrolling with the ground track
    @inputs begin
        g::Vec{7}, [description = "Pose of this aircraft (qw, qx, qy, qz, x, y, z)"]
        g0::Vec{7}, [description = "Pose of the reference aircraft"]
    end
    @outputs begin
        pose::Vec{7}
        field::Vec{7}
        stripes::Vec{7}
    end
    @parameters begin
        dx::Real = 0.0, [unit = "m", description = "Formation offset, x (north)"]
        dy::Real = 0.0, [unit = "m", description = "Formation offset, y (west)"]
        dz::Real = 0.0, [unit = "m", description = "Height of the framed aircraft in the view"]
        z0::Real = 0.0, [unit = "m", description = "Start altitude of the reference aircraft"]
        depth::Real = 150.0, [unit = "m"]
        reach::Real = 100.0, [unit = "m", min = 0]
        period::Real = 50.0, [unit = "m", min = 1.0e-3]
    end
    @equations begin
        pose[1] ~ g[1]
        pose[2] ~ g[2]
        pose[3] ~ g[3]
        pose[4] ~ g[4]
        pose[5] ~ g[5] - g0[5] + dx
        pose[6] ~ g[6] - g0[6] + dy
        pose[7] ~ g[7] - g0[7] + dz
        field[1] ~ 1.0
        field[2] ~ 0.0
        field[3] ~ 0.0
        field[4] ~ 0.0
        field[5] ~ -g0[5]
        field[6] ~ -g0[6]
        field[7] ~ dz - g0[7]
        stripes[1] ~ 1.0
        stripes[2] ~ 0.0
        stripes[3] ~ 0.0
        stripes[4] ~ 0.0
        stripes[5] ~ -(g0[5] - period * floor(g0[5] / period))
        stripes[6] ~ -(g0[6] - period * floor(g0[6] / period))
        stripes[7] ~ dz + clamp(z0 - g0[7], -reach, reach) - depth
    end
end
