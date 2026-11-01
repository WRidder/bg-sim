@block TerrainSurface begin
    # Smooth terrain as an analytic height field, for wheels and contacts that need the ground
    # under a moving point: a signal source of the TANGENT PLANE at the query point `g[5:7]`, in the
    # format of `ContactSurface` (`o`, `fr`), so a `Tyre`, `RollingDisk` or `ContactPoint` takes
    # it unchanged. Feed `g` the wheel carrier pose: the plane is the
    # tangent plane at the point straight below it.
    #
    #   z = h(x, y) = h0 + sx x + sy y + sum_i a_i cos(kx_i x + ky_i y + ph_i)
    #   n = (-h_x, -h_y, 1)/sqrt(1 + h_x^2 + h_y^2)
    #   o = (x, y, h(x, y)) at (x, y) = (g[5], g[6]),  fr = (n, t1, t2),  t1 = (1, 0, h_x)/|.|,  t2 = n x t1
    #
    # The height field is exact and cheap to evaluate anywhere, so a host can draw the same
    # ground the model drives on. Using the tangent plane at the point below the wheel centre
    # instead of at the contact point (which lies `R sin(slope)` uphill) errs by about
    # `kappa d^2 / 2` in height, `kappa` the curvature (`a k^2`) and `d` that offset: well under
    # a millimetre for hills that are long compared with the wheel. `N` components (constant).
    @constants N::Int = 2
    @inputs g::Vec{7}, [description = "Pose of the query point (the wheel carrier pose, D-MB6 chart); only its position x, y = g[5], g[6] is used"]
    @outputs begin
        o::Vec{3}, [unit = "m", description = "Point of the terrain below the query point"]
        fr::Vec{9}, [unit = "1", description = "Tangent-plane frame (n, t1, t2) at that point"]
        hq::Real, [unit = "m", description = "Terrain height below the query point"]
        slope::Real, [unit = "rad", description = "Inclination of the terrain below the query point, atan(|grad h|)"]
    end
    @parameters begin
        h0::Real = 0.0, [unit = "m", description = "Base height"]
        sx::Real = 0.0, [unit = "1", description = "Constant slope dh/dx"]
        sy::Real = 0.0, [unit = "1", description = "Constant slope dh/dy"]
        a::Vec{N} = [0.0, 0.0], [unit = "m", description = "Amplitude of each cosine component"]
        kx::Vec{N} = [0.1, 0.0], [unit = "rad/m", description = "Wave number of each component along x"]
        ky::Vec{N} = [0.0, 0.1], [unit = "rad/m", description = "Wave number of each component along y"]
        ph::Vec{N} = [0.0, 0.0], [unit = "rad", description = "Phase of each component"]
    end
    @variables begin
        c::Vec{N}, [unit = "1", description = "cos of each component's phase at the query point"]
        sn::Vec{N}, [unit = "1", description = "sin of each component's phase at the query point"]
        akx::Vec{N}, [unit = "1", description = "a_i kx_i"]
        aky::Vec{N}, [unit = "1", description = "a_i ky_i"]
        hx::Real = 0.0, [unit = "1", description = "dh/dx at the query point"]
        hy::Real = 0.0, [unit = "1", description = "dh/dy at the query point"]
        nn::Real = 1.0, [unit = "1", description = "sqrt(1 + hx^2 + hy^2)"]
        tn::Real = 1.0, [unit = "1", description = "sqrt(1 + hx^2)"]
    end
    @equations begin
        for i in 1:N
            c[i] ~ cos(kx[i] * g[5] + ky[i] * g[6] + ph[i])
            sn[i] ~ sin(kx[i] * g[5] + ky[i] * g[6] + ph[i])
            akx[i] ~ a[i] * kx[i]
            aky[i] ~ a[i] * ky[i]
        end
        hq ~ h0 + sx * g[5] + sy * g[6] + dot(a, c)
        hx ~ sx - dot(akx, sn)
        hy ~ sy - dot(aky, sn)
        nn ~ sqrt(1 + hx * hx + hy * hy)
        tn ~ sqrt(1 + hx * hx)
        slope ~ atan(sqrt(hx * hx + hy * hy))
        o[1] ~ g[5]
        o[2] ~ g[6]
        o[3] ~ hq
        fr[1] ~ -hx / nn
        fr[2] ~ -hy / nn
        fr[3] ~ 1 / nn
        fr[4] ~ 1 / tn
        fr[5] ~ 0.0
        fr[6] ~ hx / tn
        fr[7] ~ fr[2] * fr[6] - fr[3] * fr[5]
        fr[8] ~ fr[3] * fr[4] - fr[1] * fr[6]
        fr[9] ~ fr[1] * fr[5] - fr[2] * fr[4]
    end
end
