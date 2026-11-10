@block AirData3D begin
    # Flight-state tap of a rocket over a round Earth (it computes, it adds no physics). Inputs
    # are the body pose in the inertial launch frame (origin on the pad, x downrange, z up, Earth
    # centre at (0, 0, -R)) and the body twist [w; v] in body axes (`DfSpatial` of the body).
    #
    #   h          altitude above the sphere, |rc| - R
    #   s          surface range: R times the angle from the pad, measured on the turning Earth
    #              (the pad moves at the angular rate `omega` about the world y axis)
    #   vw         inertial velocity (world), speed |vw|, fpa the flight-path angle above the local
    #              horizontal (space-fixed, as the AS-506 report gives it)
    #   va         velocity relative to the air, which turns with the Earth: vw - omega x rc, in body
    #              axes (the drag reads it), and its magnitude v_rel (the Earth-fixed speed)
    #   theta      elevation of the body x axis above the launch-site horizontal (what the pitch
    #              program commands), theta_deg in degrees
    #
    # `omega` is the rate at which the air (and the ground) turns in the plane of flight: the
    # Earth's rotation resolved into that plane, v_pad / R.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw, qx, qy, qz, x, y, z)"]
        V::Vec{6}, [description = "Body twist [w; v] in body axes"]
    end
    @parameters begin
        R::Real = 6378165.0, [unit = "m", description = "Earth radius"]
        omega::Real = 0.0, [unit = "rad/s", description = "Rotation rate of the air about the world y axis"]
        v_eps::Real = 1.0e-3, [unit = "m/s", description = "Speed floor for directions at rest"]
    end
    @variables begin
        s2::Real, [description = "Squared quaternion norm"]
        Rm::Mat{3,3}, [description = "Rotation body to world"]
        rc::Vec{3}, [unit = "m"]
        r::Real, [unit = "m"]
        vaw::Vec{3}, [unit = "m/s", description = "Air-relative velocity, world"]
    end
    @outputs begin
        h::Real, [unit = "m"]
        s::Real, [unit = "m"]
        vw::Vec{3}, [unit = "m/s"]
        speed::Real, [unit = "m/s"]
        fpa::Real, [unit = "rad"]
        fpa_deg::Real
        va::Vec{3}, [unit = "m/s"]
        v_rel::Real, [unit = "m/s"]
        theta::Real, [unit = "rad"]
        theta_deg::Real
        h_km::Real
        s_km::Real
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
        h ~ r - R
        h_km ~ h / 1000
        for k in 1:3
            vw[k] ~ Rm[k, 1] * V[4] + Rm[k, 2] * V[5] + Rm[k, 3] * V[6]
        end
        vaw[1] ~ vw[1] - omega * rc[3]
        vaw[2] ~ vw[2]
        vaw[3] ~ vw[3] + omega * rc[1]
        for k in 1:3
            va[k] ~ Rm[1, k] * vaw[1] + Rm[2, k] * vaw[2] + Rm[3, k] * vaw[3]
        end
        speed ~ sqrt(vw[1] * vw[1] + vw[2] * vw[2] + vw[3] * vw[3] + v_eps * v_eps)
        v_rel ~ sqrt(vaw[1] * vaw[1] + vaw[2] * vaw[2] + vaw[3] * vaw[3] + v_eps * v_eps)
        fpa ~ asin((rc[1] * vw[1] + rc[2] * vw[2] + rc[3] * vw[3]) / (r * speed))
        fpa_deg ~ fpa * 180 / pi
        s ~ R * (atan(rc[1] / r, rc[3] / r) - omega * t)
        s_km ~ s / 1000
        theta ~ atan(Rm[3, 1], Rm[1, 1])
        theta_deg ~ theta * 180 / pi
    end
end
