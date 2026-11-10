@block LunarSurface3D begin
    # The lunar surface as a sphere, for `ContactPoint`: a signal source of the TANGENT PLANE of
    # the sphere straight below the query point (the footpad), in the format of the stdlib
    # `ContactSurface` (`o`, `fr`). The stdlib `ContactSurface` is one fixed plane and
    # `TerrainSurface` a height field over a plane; over the 480 km of the powered descent the
    # site's tangent plane lies tens of kilometres above the Moon's surface (the vehicle would be
    # "inside" it), so the contact needs the sphere itself.
    #
    #   n  = (p - c) / |p - c|          outward normal (the centre c = (0, 0, -R))
    #   o  = c + R n                    the point of the sphere below p
    #   t1 = e_y x n / |e_y x n|        downrange tangent,   t2 = n x t1
    @inputs g::Vec{7}, [description = "Pose of the query point (only its position is used)"]
    @parameters R::Real = 1737400.0, [unit = "m", description = "Radius of the Moon (centre at (0, 0, -R))"]
    @variables begin
        rq::Real, [unit = "m"]
        n::Vec{3}
        nt::Real
    end
    @outputs begin
        o::Vec{3}, [unit = "m"]
        fr::Vec{9}, [unit = "1"]
    end
    @equations begin
        rq ~ sqrt(g[5] * g[5] + g[6] * g[6] + (g[7] + R) * (g[7] + R))
        n[1] ~ g[5] / rq
        n[2] ~ g[6] / rq
        n[3] ~ (g[7] + R) / rq
        o[1] ~ R * n[1]
        o[2] ~ R * n[2]
        o[3] ~ R * n[3] - R
        nt ~ sqrt(n[3] * n[3] + n[1] * n[1])
        fr[1] ~ n[1]
        fr[2] ~ n[2]
        fr[3] ~ n[3]
        fr[4] ~ n[3] / nt
        fr[5] ~ 0.0
        fr[6] ~ -n[1] / nt
        fr[7] ~ n[2] * fr[6] - n[3] * fr[5]
        fr[8] ~ n[3] * fr[4] - n[1] * fr[6]
        fr[9] ~ n[1] * fr[5] - n[2] * fr[4]
    end
end
