@block AscentGuidance begin
    # Ascent guidance of the lunar module (TN D-6846): a vertical rise until the radial rate
    # reaches `vrise` (40 ft/s, a latched event), then the insertion phase, Apollo's "linear
    # guidance": the radial acceleration command is linear in time and meets the target radius
    # r_T = R + h_T and radial rate rdot_T after the time to go
    #
    #     a_r = 6 (r_T - r - rdot tgo) / tgo^2 - 2 (rdot_T - rdot) / tgo,
    #     tgo = (m c / T) (1 - exp(-v_go / c))   (the rocket equation on the velocity to be gained),
    #
    # the thrust supplies a_r plus gravity less the centrifugal term, and whatever thrust
    # acceleration is left goes downrange (the ascent engine is not throttleable). The engine is
    # cut (latched event) when the horizontal velocity plus the tail-off still to come (the lagged
    # thrust adds T t_tail / m after the cutoff) reaches the target `vh_T`, or when the
    # propellant is gone. Frame: the inertial site frame, the flight in its x-z plane.
    # `steer = 0` keeps the vertical rise for ever (the vacuum check).
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z) in the site frame"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
        m::Real, [unit = "kg"]
        T::Real, [unit = "N", description = "Current thrust"]
        prop::Real, [unit = "kg", description = "Usable propellant left"]
    end
    @parameters begin
        mu::Real = 4.9028e12, [unit = "m^3/s^2"]
        R::Real = 1737400.0, [unit = "m"]
        gscale::Real = 1.0
        T_aps::Real = 15409.0, [unit = "N", description = "Ascent engine thrust"]
        c::Real = 3034.0, [unit = "m/s", description = "Effective exhaust velocity"]
        h_T::Real = 18288.0, [unit = "m", description = "Insertion altitude"]
        rdot_T::Real = 9.81, [unit = "m/s", description = "Insertion radial rate"]
        vh_T::Real = 1687.0, [unit = "m/s", description = "Insertion horizontal velocity"]
        vrise::Real = 12.19, [unit = "m/s", description = "Radial rate that ends the vertical rise"]
        steer::Real = 1.0, [description = "0: hold the vertical rise (no pitch-over, no cutoff)"]
        tgo_min::Real = 1.0, [unit = "s", description = "Floor of the time to go"]
        t_tail::Real = 0.2, [unit = "s", description = "Thrust tail-off time constant: the cutoff anticipates the velocity T t_tail / m it still adds"]
        T_min::Real = 1.0, [unit = "N", description = "Thrust floor (no division by zero)"]
    end
    @variables begin
        insert::Real = 0.0, [description = "1 after the pitch-over (latched)"]
        on::Real = 1.0, [description = "1 while the engine burns (latched)"]
        s2::Real
        vw::Vec{3}, [unit = "m/s"]
        rc::Vec{3}, [unit = "m"]
        r::Real, [unit = "m"]
        er::Vec{3}
        eh::Vec{3}
        nh::Real
        rdot::Real, [unit = "m/s"]
        vh::Real, [unit = "m/s"]
        aT::Real, [unit = "m/s^2"]
        vgo::Real, [unit = "m/s"]
        ar::Real, [unit = "m/s^2"]
        fr::Real, [unit = "m/s^2"]
        fh::Real, [unit = "m/s^2"]
        zv::Real, [unit = "m/s"]
        zc::Real, [unit = "m/s"]
        zf::Real, [unit = "kg"]
    end
    @outputs begin
        u::Vec{3}, [description = "Commanded thrust direction (world, unit)"]
        T_cmd::Real, [unit = "N"]
        tgo::Real, [unit = "s"]
    end
    @equations begin
        ddt(insert) ~ 0.0
        ddt(on) ~ 0.0
        s2 ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        vw[1] ~ ((g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) * V[4] + 2 * (g[2] * g[3] - g[1] * g[4]) * V[5] + 2 * (g[2] * g[4] + g[1] * g[3]) * V[6]) / s2
        vw[2] ~ (2 * (g[2] * g[3] + g[1] * g[4]) * V[4] + (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) * V[5] + 2 * (g[3] * g[4] - g[1] * g[2]) * V[6]) / s2
        vw[3] ~ (2 * (g[2] * g[4] - g[1] * g[3]) * V[4] + 2 * (g[3] * g[4] + g[1] * g[2]) * V[5] + (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) * V[6]) / s2
        rc[1] ~ g[5]
        rc[2] ~ g[6]
        rc[3] ~ g[7] + R
        r ~ sqrt(rc[1] * rc[1] + rc[2] * rc[2] + rc[3] * rc[3])
        for k in 1:3
            er[k] ~ rc[k] / r
        end
        # downrange horizontal: e_y x e_r, normalised
        nh ~ sqrt(er[3] * er[3] + er[1] * er[1])
        eh[1] ~ er[3] / nh
        eh[2] ~ 0.0
        eh[3] ~ -er[1] / nh
        rdot ~ vw[1] * er[1] + vw[2] * er[2] + vw[3] * er[3]
        vh ~ vw[1] * eh[1] + vw[2] * eh[2] + vw[3] * eh[3]
        aT ~ max(T, T_min) / m
        vgo ~ sqrt((vh_T - vh) * (vh_T - vh) + (rdot_T - rdot) * (rdot_T - rdot))
        tgo ~ max(m * c / max(T, T_min) * (1 - exp(-vgo / c)), tgo_min)
        ar ~ 6 * (R + h_T - r - rdot * tgo) / (tgo * tgo) - 2 * (rdot_T - rdot) / tgo
        fr ~ min(ar + gscale * mu / (r * r) - vh * vh / r, aT)
        fh ~ sqrt(max(aT * aT - fr * fr, 0.0))
        for k in 1:3
            u[k] ~ ifelse(insert > 0.5, (fr * er[k] + fh * eh[k]) / sqrt(fr * fr + fh * fh), er[k])
        end
        T_cmd ~ on * T_aps
        zv ~ ifelse(insert > 0.5, -vrise, steer * (rdot - vrise))
        zc ~ ifelse(on > 0.5, steer * (vh + t_tail * T / m - vh_T), -vh_T)
        zf ~ ifelse(on > 0.5, -prop, -1.0)
    end
    @events begin
        zv > 0 => begin
            reinit(insert, 1.0)
        end
        zc > 0 => begin
            reinit(on, 0.0)
        end
        zf > 0 => begin
            reinit(on, 0.0)
        end
    end
end
