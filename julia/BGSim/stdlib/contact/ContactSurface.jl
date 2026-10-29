@block ContactSurface begin
    # Rigid plane for `ContactPoint` (F11, J-MB13): a point `o` on the plane and a normal, both
    # in the world frame. It is a pure signal source (no port), so one surface feeds any number
    # of contact points, and the plane is not duplicated in every point.
    #
    # Two signals describe the plane (separate vectors because a position (m) and a direction
    # (1) must not share one unit):
    #   `o`  = (x, y, z) the plane origin, in m;
    #   `fr` = (n, t1, t2) three unit vectors, 9 numbers: the outward normal `n` (the side the
    #          bodies live on) and two orthonormal tangents with `n = t1 x t2` (right-handed
    #          `t1, t2, n`).
    # The normal parameter need not be unit (it is normalised). The tangents are derived from
    # the normal (cross with the world z axis, or with x when the normal is within acos(0.9)
    # of the z axis) and then turned about `n` by `heading`, so the two scalar
    # friction dampers of `ContactPoint` can be aligned with a known sliding direction (the
    # box friction of the two scalar 1-junctions is not isotropic).
    @parameters begin
        ox::Real = 0.0, [unit = "m", description = "Plane origin x (world)"]
        oy::Real = 0.0, [unit = "m", description = "Plane origin y (world)"]
        oz::Real = 0.0, [unit = "m", description = "Plane origin z (world)"]
        nx::Real = 0.0, [unit = "1", description = "Plane normal x (world, normalised internally)"]
        ny::Real = 0.0, [unit = "1", description = "Plane normal y (world, normalised internally)"]
        nz::Real = 1.0, [unit = "1", description = "Plane normal z (world, normalised internally)"]
        heading::Real = 0.0, [unit = "rad", description = "Rotation of the two friction tangents about the normal"]
    end
    @variables begin
        nn::Real = 1.0, [unit = "1", description = "Length of the normal parameter vector"]
        ux::Real = 0.0, [unit = "1", description = "Unit normal x"]
        uy::Real = 0.0, [unit = "1", description = "Unit normal y"]
        uz::Real = 1.0, [unit = "1", description = "Unit normal z"]
        ax::Real = 0.0, [unit = "1", description = "Reference axis x (z unless the normal is nearly vertical)"]
        az::Real = 1.0, [unit = "1", description = "Reference axis z"]
        bx::Real = 0.0, [unit = "1", description = "Unrotated tangent x (a x n, normalised)"]
        by::Real = 1.0, [unit = "1", description = "Unrotated tangent y"]
        bz::Real = 0.0, [unit = "1", description = "Unrotated tangent z"]
        bn::Real = 1.0, [unit = "1", description = "Length of a x n"]
    end
    @outputs begin
        o::Vec{3}, [unit = "m"]
        fr::Vec{9}, [unit = "1"]
    end
    @equations begin
        nn ~ sqrt(nx * nx + ny * ny + nz * nz)
        ux ~ nx / nn
        uy ~ ny / nn
        uz ~ nz / nn
        # Reference axis: z, or x when the normal is within acos(0.9) of the z axis.
        ax ~ ifelse(abs(nz) < 0.9 * nn, 0.0, 1.0)
        az ~ ifelse(abs(nz) < 0.9 * nn, 1.0, 0.0)
        bn ~ sqrt(az * az * uy * uy + (az * ux - ax * uz) * (az * ux - ax * uz) + ax * ax * uy * uy)
        bx ~ (-az * uy) / bn
        by ~ (az * ux - ax * uz) / bn
        bz ~ (ax * uy) / bn
        o[1] ~ ox
        o[2] ~ oy
        o[3] ~ oz
        fr[1] ~ ux
        fr[2] ~ uy
        fr[3] ~ uz
        # t1 = cos(h) b + sin(h) (n x b); t2 = n x t1.
        fr[4] ~ cos(heading) * bx + sin(heading) * (uy * bz - uz * by)
        fr[5] ~ cos(heading) * by + sin(heading) * (uz * bx - ux * bz)
        fr[6] ~ cos(heading) * bz + sin(heading) * (ux * by - uy * bx)
        fr[7] ~ uy * fr[6] - uz * fr[5]
        fr[8] ~ uz * fr[4] - ux * fr[6]
        fr[9] ~ ux * fr[5] - uy * fr[4]
    end
end
