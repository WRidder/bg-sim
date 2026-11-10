@block LMState begin
    # Flight-state tap of the lunar module over a round Moon (it computes, it adds no physics).
    # Inputs are the body pose in the inertial site frame (origin at the landing site, x
    # downrange, z up, the Moon's centre at (0, 0, -R)) and the body twist [w; v].
    #
    #   h, h_ft     altitude of the centre of mass above the sphere (the guidance's altitude)
    #   s, s_km     surface range from the landing site (negative: still uprange)
    #   rdot        radial velocity (altitude rate, positive up), rdot_fps in ft/s
    #   vh          horizontal velocity downrange, vh_fps in ft/s; vy the cross-range velocity
    #   speed       inertial speed
    #   tilt_deg    angle of the thrust axis (body x) from the local vertical
    #   h_pad       height of the lowest footpad sole above the sphere: the four pads sit at
    #               (-d_cg, +-tread, 0) and (-d_cg, 0, +-tread) in body axes
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
    end
    @parameters begin
        R::Real = 1737400.0, [unit = "m", description = "Radius of the Moon"]
        d_cg::Real = 1.95, [unit = "m", description = "Centre of mass above the footpad soles"]
        tread::Real = 4.256, [unit = "m", description = "Footpad centre from the X axis"]
    end
    @variables begin
        s2::Real
        Rm::Mat{3,3}
        rc::Vec{3}, [unit = "m"]
        r::Real, [unit = "m"]
        er::Vec{3}
        eh::Vec{3}
        nh::Real
        vw::Vec{3}, [unit = "m/s"]
        hp::Vec{4}, [unit = "m", description = "Height of each footpad"]
    end
    @outputs begin
        h::Real, [unit = "m"]
        h_ft::Real
        h_km::Real
        s::Real, [unit = "m"]
        s_km::Real
        rdot::Real, [unit = "m/s"]
        rdot_fps::Real
        vh::Real, [unit = "m/s"]
        vh_fps::Real
        vy::Real, [unit = "m/s"]
        speed::Real, [unit = "m/s"]
        tilt_deg::Real
        h_pad::Real, [unit = "m"]
    end
    @equations begin
        s2 ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        Rm[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s2
        Rm[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s2
        Rm[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s2
        Rm[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s2
        Rm[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s2
        Rm[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s2
        Rm[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s2
        Rm[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s2
        Rm[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s2
        rc[1] ~ g[5]
        rc[2] ~ g[6]
        rc[3] ~ g[7] + R
        r ~ sqrt(rc[1] * rc[1] + rc[2] * rc[2] + rc[3] * rc[3])
        for k in 1:3
            er[k] ~ rc[k] / r
            vw[k] ~ Rm[k, 1] * V[4] + Rm[k, 2] * V[5] + Rm[k, 3] * V[6]
        end
        nh ~ sqrt(er[3] * er[3] + er[1] * er[1])
        eh[1] ~ er[3] / nh
        eh[2] ~ 0.0
        eh[3] ~ -er[1] / nh
        h ~ r - R
        h_ft ~ h / 0.3048
        h_km ~ h / 1000
        s ~ R * atan(rc[1] / r, rc[3] / r)
        s_km ~ s / 1000
        rdot ~ vw[1] * er[1] + vw[2] * er[2] + vw[3] * er[3]
        rdot_fps ~ rdot / 0.3048
        vh ~ vw[1] * eh[1] + vw[2] * eh[2] + vw[3] * eh[3]
        vh_fps ~ vh / 0.3048
        vy ~ vw[2]
        speed ~ sqrt(vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3])
        tilt_deg ~ acos(clamp(Rm[1, 1] * er[1] + Rm[2, 1] * er[2] + Rm[3, 1] * er[3], -1.0, 1.0)) * 180 / pi
        # pad k at body b_k: world rc + Rm b_k; height |.| - R
        hp[1] ~ sqrt((rc[1] - d_cg * Rm[1, 1] + tread * Rm[1, 2]) ^ 2 + (rc[2] - d_cg * Rm[2, 1] + tread * Rm[2, 2]) ^ 2 + (rc[3] - d_cg * Rm[3, 1] + tread * Rm[3, 2]) ^ 2) - R
        hp[2] ~ sqrt((rc[1] - d_cg * Rm[1, 1] - tread * Rm[1, 2]) ^ 2 + (rc[2] - d_cg * Rm[2, 1] - tread * Rm[2, 2]) ^ 2 + (rc[3] - d_cg * Rm[3, 1] - tread * Rm[3, 2]) ^ 2) - R
        hp[3] ~ sqrt((rc[1] - d_cg * Rm[1, 1] + tread * Rm[1, 3]) ^ 2 + (rc[2] - d_cg * Rm[2, 1] + tread * Rm[2, 3]) ^ 2 + (rc[3] - d_cg * Rm[3, 1] + tread * Rm[3, 3]) ^ 2) - R
        hp[4] ~ sqrt((rc[1] - d_cg * Rm[1, 1] - tread * Rm[1, 3]) ^ 2 + (rc[2] - d_cg * Rm[2, 1] - tread * Rm[2, 3]) ^ 2 + (rc[3] - d_cg * Rm[3, 1] - tread * Rm[3, 3]) ^ 2) - R
        h_pad ~ min(min(hp[1], hp[2]), min(hp[3], hp[4]))
    end
end
