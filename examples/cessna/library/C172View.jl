@block C172View begin
    # Scene helper (no physics): the 3D view keeps a reference aircraft framed by moving the
    # world instead of the camera (as the f16 example's F16View). Every pose is relative to the
    # reference aircraft's position g0 (for the reference itself, g = g0):
    #
    #   pose       this aircraft: its attitude, at (its position - the reference's) + (dx, dy, dz)
    #              (a formation slot, so aircraft that start together do not overlap)
    #   field      the airfield (runway, taxiway, buildings): the world shifted by -g0, so it stays
    #              where it is relative to the aircraft
    #   ground     a reference floor for flight far from the field: `depth` below the start altitude
    #              z0, under the aircraft, following climbs and descents up to `reach`; it does not
    #              move sideways, so its edges stay put
    #   stripes_x  its stripes across x (lines of constant x) and across y, at the floor's height,
    #   stripes_y  scrolling with the ground track: each set along its own axis only, by the ground
    #              track wrapped into one stripe spacing `period` (-period/2 to period/2, 0 at the
    #              start), so the stripes stay on the floor. A wrap jumps by a whole period, which the
    #              pattern hides; the scene's bindings declare the period, so the 3D view interpolates
    #              across the wrap the short way instead of sliding the stripes back for a frame
    @inputs begin
        g::Vec{7}, [description = "Pose of this aircraft (qw, qx, qy, qz, x, y, z)"]
        g0::Vec{7}, [description = "Pose of the reference aircraft"]
    end
    @outputs begin
        pose::Vec{7}
        field::Vec{7}
        ground::Vec{7}
        stripes_x::Vec{7}
        stripes_y::Vec{7}
    end
    @parameters begin
        dx::Real = 0.0, [unit = "m", description = "Formation offset, x (north)"]
        dy::Real = 0.0, [unit = "m", description = "Formation offset, y (west)"]
        dz::Real = 0.0, [unit = "m", description = "Height of the framed aircraft in the view"]
        z0::Real = 0.0, [unit = "m", description = "Start altitude of the reference aircraft"]
        depth::Real = 150.0, [unit = "m"]
        reach::Real = 100.0, [unit = "m", min = 0]
        period::Real = 50.0, [unit = "m", min = 1.0e-3, description = "Floor stripe spacing"]
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
        field[1] ~ 1.0
        field[2] ~ 0.0
        field[3] ~ 0.0
        field[4] ~ 0.0
        field[5] ~ -g0[5]
        field[6] ~ -g0[6]
        field[7] ~ dz - g0[7]
        zf ~ dz + clamp(z0 - g0[7], -reach, reach) - depth
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
